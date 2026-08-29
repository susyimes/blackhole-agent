"""Consume shipped leftovers against the origin ledger, not a lagging checkout.

``capability.kernel-leftover`` already drops leftovers whose closer is proved
on the working-tree ledger. Harvest still re-injects a shipped leftover when
the controller checkout lags origin: leftover satisfaction read only that
checkout, so ``capability.mcp-recovery-plane`` on the published tip left
``Optional later work is watching mixed MCP+absorbed goals in the recovery
plane so a red MCP hop is healed.`` open as genesis fuel. Cheap 402-local
ticks then bound the leftover from ``state.goal`` and closed the mission
without consuming the leftover claim.

This module closes that harvest hole:

- leftover satisfaction merges the origin/lineage-tip ledger
- a lagging checkout ledger still sees the leftover when the closer is absent
- harvest drops a leftover whose closer is proved only on the origin tip
- leftover-prefixed goals bound from ``state.goal`` consume the leftover claim
- an unrelated leftover stays in fuel
"""

from __future__ import annotations

import json
import subprocess
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
from blackhole_agent.experience_fuel import harvest_experience
from blackhole_agent.kernel_leftover import (
    LEFTOVER_CLASS,
    LEFTOVER_GOAL_PREFIX,
    _write_leftover_mission,
    campaign_binds_leftover,
    consume_bound_leftover,
    leftover_claim_consumed,
    leftover_is_open,
    leftover_marker_ids,
    leftover_satisfied_by,
    leftover_summary_from_goal,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign

SCHEMA_VERSION = 1
LEFTOVER_LINEAGE_ID = "capability.leftover-lineage-plane"
MCP_RECOVERY_ID = "capability.mcp-recovery-plane"
HARVESTED_MCP_RECOVERY_LEFTOVER = (
    "Optional later work is watching mixed MCP+absorbed goals in the "
    "recovery plane so a red MCP hop is healed."
)
UNRELATED_LEFTOVER = (
    "Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter."
)
LEFTOVER_LINEAGE_GOAL = (
    "Repair leftover harvest isolation of the origin ledger: a shipped leftover "
    "still enters genesis fuel because leftover satisfaction only reads the "
    "lagging checkout ledger."
)
LEFTOVER_LINEAGE_DONE_WHEN = (
    f"capability_exists:{LEFTOVER_LINEAGE_ID};"
    f"capability_proved:{LEFTOVER_LINEAGE_ID};"
    "no_skill_route"
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def leftover_lineage_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.leftover_lineage import "
        "builtin_leftover_lineage_proof; r=builtin_leftover_lineage_proof(); "
        "assert r['ok'] and r.get('action')=='leftover_lineage' "
        "and r.get('passed_count',0) >= 8 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_leftover_lineage_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LEFTOVER_LINEAGE_ID,
        name="Leftover origin-ledger harvest",
        description=(
            "Leftover harvest consults the origin ledger: a shipped leftover "
            "whose closer is proved only on the published tip leaves genesis "
            "fuel, a lagging checkout still sees the leftover without that "
            "closer, leftover-prefixed cheap-finality campaigns consume the "
            "claim, and unrelated leftovers stay open."
        ),
        kind="python",
        entry="blackhole_agent.leftover_lineage:builtin_leftover_lineage_proof",
        proof_command=leftover_lineage_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-leftover",
            "capability.kernel-class-closure",
        ),
        behavior_paths=(
            "src/blackhole_agent/leftover_lineage.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/experience_fuel.py",
            "src/blackhole_agent/kernel_class_closure.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Leftover harvest no longer reopens shipped work from a lagging "
            "checkout: origin-ledger closers consume the leftover, leftover-"
            "prefixed state.goal campaigns stamp the claim, and unrelated "
            "leftovers stay in fuel."
        ),
        tags=("leftover", "harvest", "ledger", "origin", "genesis", "experience-fuel"),
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
            description="Proved leftover closer used by leftover-lineage proof.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)


def _write_loop_lineage(root: Path, lineage_ref: str) -> None:
    path = Path(root) / ".blackhole-agent" / "unbound" / "continuous-loop.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"lineage_ref": lineage_ref, "status": "running_mission"}) + "\n",
        encoding="utf-8",
    )


def _git_commit_ledger(root: Path) -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Blackhole Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "blackhole@example.invalid"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "origin leftover closer"], cwd=root, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return (sha.stdout or "").strip()


def _lag_checkout_ledger(root: Path) -> CapabilityLedger:
    path = default_ledger_path(root)
    lagged = CapabilityLedger()
    register_capability(
        lagged,
        Capability(
            id="capability.fixture-lagging-checkout",
            name="Lagging checkout stamp",
            description="Unrelated proved stamp on a lagging checkout ledger.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, lagged)
    return lagged


def builtin_leftover_lineage_proof() -> dict[str, Any]:
    """Hermetic proof: origin leftover closers drop harvest; lagging checkouts do not."""

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LEFTOVER_LINEAGE_ID in LOCAL_DENYLIST
    markers = leftover_marker_ids(LEFTOVER_LINEAGE_GOAL)
    checks["leftover_marker"] = markers == (LEFTOVER_LINEAGE_ID,)
    checks["recovery_leftover_stays_on_heal_plane"] = leftover_marker_ids(
        HARVESTED_MCP_RECOVERY_LEFTOVER
    ) == (MCP_RECOVERY_ID,)
    prefixed = LocalCampaign(
        goal=LEFTOVER_GOAL_PREFIX + HARVESTED_MCP_RECOVERY_LEFTOVER,
        bound_from="state.goal+state.done_when",
    )
    class_bound = LocalCampaign(
        goal=HARVESTED_MCP_RECOVERY_LEFTOVER,
        bound_from=f"experience:{LEFTOVER_CLASS}",
    )
    checks["prefixed_goal_binds_leftover"] = campaign_binds_leftover(prefixed) is True
    checks["class_source_still_binds"] = campaign_binds_leftover(class_bound) is True
    checks["unrelated_campaign_does_not_bind"] = campaign_binds_leftover(
        LocalCampaign(goal="Operator growth goal.", bound_from="state.goal")
    ) is False

    with tempfile.TemporaryDirectory(prefix="leftover-lineage-origin-") as tmp:
        root = Path(tmp)
        _register_proved(root, MCP_RECOVERY_ID, name="MCP recovery")
        sha = _git_commit_ledger(root)
        lagged = _lag_checkout_ledger(root)
        _write_loop_lineage(root, sha)
        _write_leftover_mission(
            root,
            mission_id="prior-mcp-recovery",
            next_step=HARVESTED_MCP_RECOVERY_LEFTOVER,
            goal="Watch mixed MCP+absorbed goals on the reliability plane.",
        )
        _write_leftover_mission(
            root,
            mission_id="prior-steward",
            next_step=UNRELATED_LEFTOVER,
        )
        checkout_open = leftover_is_open(
            HARVESTED_MCP_RECOVERY_LEFTOVER,
            root,
            source_mission_id="prior-mcp-recovery",
            ledger=lagged,
        )
        fuel = harvest_experience(root, limit=5)
        reason = leftover_satisfied_by(
            HARVESTED_MCP_RECOVERY_LEFTOVER,
            root,
            source_mission_id="prior-mcp-recovery",
        )
        origin_open = leftover_is_open(
            HARVESTED_MCP_RECOVERY_LEFTOVER,
            root,
            source_mission_id="prior-mcp-recovery",
        )
        leftover_summaries = tuple(
            item.summary for item in fuel.candidates if item.class_id == LEFTOVER_CLASS
        )
        stamped = leftover_claim_consumed(root, HARVESTED_MCP_RECOVERY_LEFTOVER)
    checks["checkout_lag_keeps_leftover_open"] = checkout_open is True
    checks["origin_ledger_consumes_recovery_leftover"] = (
        origin_open is False
        and reason.startswith(f"ledger:{MCP_RECOVERY_ID}")
        and stamped is True
    )
    checks["harvest_drops_origin_closed_leftover"] = not any(
        HARVESTED_MCP_RECOVERY_LEFTOVER in summary for summary in leftover_summaries
    )
    checks["unrelated_leftover_stays_open"] = any(
        "STEWARDSHIP_STACK" in summary for summary in leftover_summaries
    )

    with tempfile.TemporaryDirectory(prefix="leftover-lineage-goal-") as tmp:
        root = Path(tmp)
        campaign = LocalCampaign(
            mission_id="cheap-close",
            goal=LEFTOVER_GOAL_PREFIX + HARVESTED_MCP_RECOVERY_LEFTOVER,
            bound_from="state.goal+state.done_when",
            handoff={},
        )
        consumed = consume_bound_leftover(root, campaign)
        summary = leftover_summary_from_goal(campaign.goal)
        stamped = leftover_claim_consumed(root, summary)
        after = leftover_is_open(summary, root)
    checks["prefixed_state_goal_consumes_claim"] = (
        consumed is True
        and stamped is True
        and after is False
        and bool((campaign.handoff or {}).get("leftover_consumed"))
    )

    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_leftover_lineage_capability()
    return {
        "ok": ok,
        "action": "leftover_lineage",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LEFTOVER_LINEAGE_GOAL,
        "done_when": LEFTOVER_LINEAGE_DONE_WHEN,
    }
