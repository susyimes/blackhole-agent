"""Drop closed-contract catalog-handoff leftovers so genesis can bind the next family.

A completed diversity-catalog mission writes
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` Harvest treated ``later genesis`` as leftover
work, so genesis rebound leftover-close cheap inventory instead of the next
unsaturated family. After FTP is proved the catalog was exhausted, so the
handoff also had nowhere to land.

This module closes that hole:

- leftover_next_step treats catalog-handoff next_steps as closed
- leftover markers consume an already-extracted handoff once this closer is
  proved
- harvest does not re-inject the handoff
- an unrelated leftover stays in fuel
- the diversity catalog names RFC 1350 TFTP as the next unsaturated family
- bind after leftover drop and a proved FTP row fills TFTP
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.experience_fuel import harvest_experience, leftover_next_step
from blackhole_agent.kernel_leftover import (
    LEFTOVER_CLASS,
    _write_leftover_mission,
    leftover_claim_consumed,
    leftover_is_open,
    leftover_marker_ids,
    leftover_satisfied_by,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.tftp_actuation import (
    TFTP_ACTUATION_DONE_WHEN,
    TFTP_ACTUATION_GOAL,
    TFTP_ACTUATION_ID,
)

SCHEMA_VERSION = 1
LEFTOVER_CATALOG_HANDOFF_ID = "capability.leftover-catalog-handoff"
HARVESTED_CATALOG_HANDOFF = (
    "Mission contract is closed; later genesis can take the next unsaturated "
    "diversity-catalog family."
)
UNRELATED_LEFTOVER = (
    "Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter."
)
LEFTOVER_CATALOG_HANDOFF_GOAL = (
    "Repair closed-contract catalog handoff: a completed mission next_step is "
    "harvested as leftover so later genesis cannot take the next unsaturated "
    "diversity-catalog family."
)
LEFTOVER_CATALOG_HANDOFF_DONE_WHEN = (
    f"capability_exists:{LEFTOVER_CATALOG_HANDOFF_ID};"
    f"capability_proved:{LEFTOVER_CATALOG_HANDOFF_ID};"
    "no_skill_route"
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def leftover_catalog_handoff_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.leftover_catalog_handoff import "
        "builtin_leftover_catalog_handoff_proof; r=builtin_leftover_catalog_handoff_proof(); "
        "assert r['ok'] and r.get('action')=='leftover_catalog_handoff' "
        "and r.get('passed_count',0) >= 10 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_leftover_catalog_handoff_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LEFTOVER_CATALOG_HANDOFF_ID,
        name="Leftover closed-contract catalog handoff",
        description=(
            "Closed-contract catalog-handoff next_steps leave genesis fuel: "
            "leftover harvest does not re-inject them, a proved closer consumes "
            "an already-extracted handoff, unrelated leftovers stay open, and "
            "later genesis binds the next unsaturated diversity-catalog family "
            "(RFC 1350 TFTP after FTP)."
        ),
        kind="python",
        entry="blackhole_agent.leftover_catalog_handoff:builtin_leftover_catalog_handoff_proof",
        proof_command=leftover_catalog_handoff_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-leftover",
            "capability.kernel-genesis-diversify",
            "capability.ftp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/leftover_catalog_handoff.py",
            "src/blackhole_agent/experience_fuel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/tftp_actuation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Closed-contract catalog-handoff leftovers no longer steal genesis: "
            "harvest drops the handoff, a proved closer consumes an already-"
            "extracted claim, unrelated leftovers stay in fuel, and later "
            "genesis binds RFC 1350 TFTP as the next unsaturated diversity-"
            "catalog family after FTP."
        ),
        tags=("leftover", "harvest", "catalog", "diversity", "genesis", "tftp"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _register_proved(root: Path, capability_id: str, *, name: str = "") -> None:
    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=name or capability_id,
            description="Proved leftover closer used by leftover-catalog-handoff proof.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)


def builtin_leftover_catalog_handoff_proof() -> dict[str, Any]:
    """Hermetic proof: catalog-handoff leftovers leave fuel; later genesis binds TFTP."""

    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import (
        _register_proved as register_catalog_proved,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
    )
    from blackhole_agent.local_mission_sovereignty import bind_local_mission

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LEFTOVER_CATALOG_HANDOFF_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LEFTOVER_CATALOG_HANDOFF_GOAL) == (
        LEFTOVER_CATALOG_HANDOFF_ID,
    )
    checks["handoff_marker"] = leftover_marker_ids(HARVESTED_CATALOG_HANDOFF) == (
        LEFTOVER_CATALOG_HANDOFF_ID,
    )
    checks["tftp_marker"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_tftp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["tftp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["handoff_is_not_leftover"] = leftover_next_step(HARVESTED_CATALOG_HANDOFF) == ""
    checks["prefixed_handoff_is_not_leftover"] = leftover_next_step(
        "None. Mission complete. " + HARVESTED_CATALOG_HANDOFF
    ) == ""
    checks["unrelated_leftover_still_extracts"] = leftover_next_step(UNRELATED_LEFTOVER) == UNRELATED_LEFTOVER
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_tftp"] = (
        len(catalog) > 46
        and catalog[46]["id"] == TFTP_ACTUATION_ID
        and catalog[45]["id"] == FTP_ACTUATION_ID
        and catalog[46]["goal"] == TFTP_ACTUATION_GOAL
        and TFTP_ACTUATION_ID in catalog[46]["done_when"]
        and catalog[46]["source"] == "genesis_bind_tftp"
    )

    class _State:
        def __init__(self, repo: Path, *, goal: str = "", done_when: str = "") -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = "leftover-catalog-handoff"
            self.stage = "genesis"

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-harvest-") as tmp:
        root = Path(tmp)
        _write_leftover_mission(
            root,
            mission_id="prior-ftp",
            next_step=HARVESTED_CATALOG_HANDOFF,
            goal="Opt in an ftp provider.",
        )
        _write_leftover_mission(
            root,
            mission_id="prior-steward",
            next_step=UNRELATED_LEFTOVER,
        )
        fuel = harvest_experience(root, limit=5)
        leftover_summaries = tuple(
            item.summary for item in fuel.candidates if item.class_id == LEFTOVER_CLASS
        )
    checks["harvest_drops_catalog_handoff"] = not any(
        "unsaturated diversity-catalog family" in summary for summary in leftover_summaries
    )
    checks["unrelated_leftover_stays_open"] = any(
        "STEWARDSHIP_STACK" in summary for summary in leftover_summaries
    )

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-open-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HARVESTED_CATALOG_HANDOFF, root)
        reason_before = leftover_satisfied_by(HARVESTED_CATALOG_HANDOFF, root)
    checks["handoff_stays_open_without_closer"] = open_before is True and reason_before == ""

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-closed-") as tmp:
        root = Path(tmp)
        _register_proved(root, LEFTOVER_CATALOG_HANDOFF_ID, name="Catalog handoff")
        reason = leftover_satisfied_by(HARVESTED_CATALOG_HANDOFF, root)
        stamped = leftover_claim_consumed(root, HARVESTED_CATALOG_HANDOFF)
        after = leftover_is_open(HARVESTED_CATALOG_HANDOFF, root)
    checks["proved_closer_consumes_handoff"] = (
        after is False
        and reason.startswith(f"ledger:{LEFTOVER_CATALOG_HANDOFF_ID}")
        and stamped is True
    )

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        _write_leftover_mission(
            root,
            mission_id="prior-ftp",
            next_step=HARVESTED_CATALOG_HANDOFF,
            goal="Opt in an ftp provider.",
        )
        for item in catalog:
            if item["id"] != TFTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
        local = bind_local_mission(_State(root), harvest=True)
    checks["exhausted_catalog_binds_tftp"] = (
        live_goal == TFTP_ACTUATION_GOAL
        and TFTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_tftp"
        and live_done == TFTP_ACTUATION_DONE_WHEN
    )
    checks["local_bind_fills_tftp"] = (
        local.goal == TFTP_ACTUATION_GOAL
        and TFTP_ACTUATION_ID in local.done_when
        and "genesis_bind_tftp" in local.source
    )

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-operator-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        kept = bind_local_mission(
            _State(root, goal="Operator growth goal.", done_when="capability_exists:repo.import-health"),
            harvest=True,
        )
    checks["preserves_operator_bind"] = (
        kept.goal == "Operator growth goal." and "state.goal" in kept.source
    )

    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_leftover_catalog_handoff_capability()
    return {
        "ok": ok,
        "action": "leftover_catalog_handoff",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LEFTOVER_CATALOG_HANDOFF_GOAL,
        "done_when": LEFTOVER_CATALOG_HANDOFF_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
