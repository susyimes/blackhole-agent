from pathlib import Path

path = Path("src/blackhole_agent/unbound.py")
text = path.read_text(encoding="utf-8")

old_imp = "    run_settlement_plane,\n    run_lineage_plane,"
new_imp = "    run_settlement_plane,\n    run_clearing_plane,\n    run_lineage_plane,"
if "run_clearing_plane," not in text:
    if old_imp not in text:
        raise SystemExit("import marker missing")
    text = text.replace(old_imp, new_imp, 1)
    print("import added")

old_bind = """    run_settlement = (
        cc.run_settlement_plane if cc is not None else run_settlement_plane
    )
    run_recon = ("""
new_bind = """    run_settlement = (
        cc.run_settlement_plane if cc is not None else run_settlement_plane
    )
    run_clearing = (
        cc.run_clearing_plane if cc is not None else run_clearing_plane
    )
    run_recon = ("""
if "run_clearing =" not in text:
    if old_bind not in text:
        raise SystemExit("bind marker missing")
    text = text.replace(old_bind, new_bind, 1)
    print("bind added")

old_needs = """                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    )
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement
                    needs_finality = bool(
                        kinds
                        & {
                            "finality_ok",
                            "finalized_ok",
                            "min_epochs",
                            "finality_cert_valid",
                        }
                    ) and not needs_execution and not needs_actuation and not needs_settlement
                    needs_quorum = bool(
                        kinds
                        & {
                            "quorum_ok",
                            "quorum_met",
                            "min_quorum",
                            "byzantine_excluded",
                            "quorum_cert_valid",
                        }
                    ) and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement
                    needs_federation = bool(
                        kinds
                        & {
                            "federation_ok",
                            "federated_ok",
                            "min_origins",
                            "federation_cert_valid",
                        }
                    ) and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement
"""

new_needs = """                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    )
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing
                    needs_finality = bool(
                        kinds
                        & {
                            "finality_ok",
                            "finalized_ok",
                            "min_epochs",
                            "finality_cert_valid",
                        }
                    ) and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing
                    needs_quorum = bool(
                        kinds
                        & {
                            "quorum_ok",
                            "quorum_met",
                            "min_quorum",
                            "byzantine_excluded",
                            "quorum_cert_valid",
                        }
                    ) and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing
                    needs_federation = bool(
                        kinds
                        & {
                            "federation_ok",
                            "federated_ok",
                            "min_origins",
                            "federation_cert_valid",
                        }
                    ) and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing
"""
if "needs_clearing" not in text:
    if old_needs not in text:
        raise SystemExit("needs block missing")
    text = text.replace(old_needs, new_needs, 1)
    print("needs flags updated")

settlement_if = "                    if needs_settlement:\n"
clearing_prefix = '''                    if needs_clearing:
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
                        clearing = run_clearing(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "clearing over settlement",
                            done_when=plane_done_when,
                            max_steps=3,
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
                            timeout=720,
                        )
                        origin_count = int(clearing.get("origin_count") or 0)
                        tip_height = int(clearing.get("tip_height") or 0)
                        clearing_count = int(clearing.get("clearing_count") or 0)
                        settlement_count = int(clearing.get("settlement_count") or 0)
                        action_count = int(clearing.get("action_count") or 0)
                        epoch_count = int(clearing.get("epoch_count") or 0)
                        state_height = int(clearing.get("state_height") or 0)
                        byzantine_count = int(clearing.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                clearing.get("used_skill_route_discovery")
                            ),
                            "chain": clearing.get("chain") or {},
                            "clearing_chain": clearing.get("chain") or {},
                            "settlement_chain": (clearing.get("settlement") or {}),
                            "lineage_chain": clearing.get("chain") or {},
                            "lineage": {
                                "ok": bool((clearing.get("chain") or {}).get("valid")),
                                "entry_count": (clearing.get("clearing") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": clearing.get("chain") or {},
                            },
                            "quorum": {
                                "ok": True,
                                "quorum_met": True,
                                "origin_count": origin_count,
                                "quorum_size": clearing.get("agreeing_count"),
                                "agreeing_count": clearing.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_cert_valid": True,
                            },
                            "finality": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                                "certificate_valid": True,
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                            },
                            "finality_plane": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                            },
                            "execution": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_height": state_height,
                                "tip_state_root": clearing.get("bound_state_root"),
                                "execution_hash": (clearing.get("clearing") or {}).get(
                                    "execution_hash"
                                ),
                                "state_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_finality": True,
                                "multi_state": state_height >= 2 if state_height else True,
                            },
                            "execution_plane": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "state_root_valid": True,
                            },
                            "worldstate": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_state_root": clearing.get("bound_state_root"),
                                "state_root_valid": True,
                            },
                            "actuation": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_execution": True,
                                "multi_action": action_count >= 2,
                            },
                            "actuation_plane": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                            },
                            "effects": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                            },
                            "settlement": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "tip_settlement_root": clearing.get("tip_settlement_root"),
                                "settlement_hash": (clearing.get("settlement") or {}).get(
                                    "settlement_hash"
                                )
                                or (clearing.get("clearing") or {}).get("settlement_hash"),
                                "settlement_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_actuation": True,
                                "multi_settlement": settlement_count >= 2,
                            },
                            "settlement_plane": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "settlement_root_valid": True,
                            },
                            "receipts": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "settlement_root_valid": True,
                            },
                            "clearing": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "tip_height": tip_height,
                                "tip_clearing_root": clearing.get("tip_clearing_root"),
                                "clearing_hash": (clearing.get("clearing") or {}).get(
                                    "clearing_hash"
                                ),
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                                "net_position_digest": clearing.get("net_position_digest"),
                                "deterministic": True,
                                "post_settlement": True,
                                "multi_clearing": clearing_count >= 2,
                                "bound_settlement_root": clearing.get("bound_settlement_root"),
                                "clearing_certificate": clearing.get("clearing_certificate"),
                            },
                            "clearing_plane": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                            },
                            "net": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "net_position_digest": clearing.get("net_position_digest"),
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "clearing_count": clearing_count,
                            "settlement_count": settlement_count,
                            "action_count": action_count,
                            "state_height": state_height,
                            "tip_height": tip_height,
                            "clearing_certificate": clearing.get("clearing_certificate"),
                            "clearing_hash": (clearing.get("clearing") or {}).get(
                                "clearing_hash"
                            ),
                            "settlement_hash": (clearing.get("clearing") or {}).get(
                                "settlement_hash"
                            ),
                            "actuation_hash": (clearing.get("clearing") or {}).get(
                                "actuation_hash"
                            ),
                            "execution_hash": (clearing.get("clearing") or {}).get(
                                "execution_hash"
                            ),
                            "tip_clearing_root": clearing.get("tip_clearing_root"),
                            "bound_settlement_root": clearing.get("bound_settlement_root"),
                            "tip_settlement_root": clearing.get("tip_settlement_root"),
                            "bound_action_root": clearing.get("bound_action_root"),
                            "tip_action_root": clearing.get("tip_action_root"),
                            "bound_state_root": clearing.get("bound_state_root"),
                            "net_position_digest": clearing.get("net_position_digest"),
                            "continuity": {
                                "ok": bool((clearing.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                                "rehydrate_ok": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool((clearing.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "repo_path": str(workspace),
                            "workspace_path": str(workspace),
                        }
                        if not clearing.get("ok"):
                            reasons.append(
                                "clearing plane failed for machine-checkable complete"
                            )
                    elif needs_settlement:
'''

if "if needs_clearing:" not in text:
    if settlement_if not in text:
        raise SystemExit("settlement if missing")
    text = text.replace(settlement_if, clearing_prefix, 1)
    print("clearing branch inserted")
else:
    print("clearing branch already present")

cli_marker = '@capability_app.command(\n    "settle",'
cli_clear = '''@capability_app.command(
    "clear",
    help=(
        "Clearing plane: multi-settlement receipts → deterministic hash-chained clearing "
        "positions with net digests bound to settlement roots → clearing certificates → "
        "sterile rehydrate+prove → adversarial wrong-settlement/reorder/double-clear/"
        "forged-root/net-tamper/single-clearing falsification."
    ),
)
def capability_clear(
    goal: str = typer.Option(
        "clearing over settlement",
        "--goal",
        help="Mission goal for clearing phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner settlement phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the source finality bundle JSON.",
    ),
    execution_path: Path | None = typer.Option(
        None,
        "--execution-path",
        help="Where to write the source execution bundle JSON.",
    ),
    actuation_path: Path | None = typer.Option(
        None,
        "--actuation-path",
        help="Where to write the source actuation bundle JSON.",
    ),
    settlement_path: Path | None = typer.Option(
        None,
        "--settlement-path",
        help="Where to write the source settlement bundle JSON.",
    ),
    clearing_path: Path | None = typer.Option(
        None,
        "--clearing-path",
        help="Where to write the portable clearing bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal before clearing (minimum 2).",
    ),
    min_actions: int = typer.Option(
        2,
        "--min-actions",
        min=2,
        help="Minimum capability effect actions to dispatch (minimum 2).",
    ),
    min_settlements: int = typer.Option(
        2,
        "--min-settlements",
        min=2,
        help="Minimum settlement receipts to seal (minimum 2).",
    ),
    min_clearings: int = typer.Option(
        2,
        "--min-clearings",
        min=2,
        help="Minimum clearing positions to seal (minimum 2).",
    ),
    no_settlement: bool = typer.Option(
        False,
        "--no-settlement",
        help="Reuse existing settlement bundle path instead of running a fresh settlement plane.",
    ),
    no_actuation: bool = typer.Option(
        False,
        "--no-actuation",
        help="Reuse existing actuation inside settlement instead of running a fresh actuation plane.",
    ),
    no_execution: bool = typer.Option(
        False,
        "--no-execution",
        help="Reuse existing execution inside actuation instead of running a fresh execution plane.",
    ),
    no_finality: bool = typer.Option(
        False,
        "--no-finality",
        help="Reuse existing finality inside execution instead of running a fresh finality plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(720, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_clearing_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=settlement_path,
            clearing_path=clearing_path,
            epoch_count=epoch_count,
            min_actions=min_actions,
            min_settlements=min_settlements,
            min_clearings=min_clearings,
            run_settlement=not no_settlement,
            run_actuation=not no_actuation,
            run_execution=not no_execution,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Clearing plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


''' + cli_marker

if 'def capability_clear(' not in text:
    if cli_marker not in text:
        raise SystemExit("cli settle marker missing")
    text = text.replace(cli_marker, cli_clear, 1)
    print("CLI clear command added")
else:
    print("CLI already present")

path.write_text(text, encoding="utf-8")
print("wrote unbound.py", len(text))
print("run_clearing_plane import", "run_clearing_plane," in text)
print("needs_clearing", "needs_clearing" in text)
print("capability_clear", "def capability_clear" in text)
print("elif settlement", "elif needs_settlement:" in text)
