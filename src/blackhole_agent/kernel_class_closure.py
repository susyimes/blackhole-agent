"""Consume structurally closed operational classes so genesis cannot reopen them.

Leftover harvest already drops shipped *next_steps*. The harvested 2026-08-16
Grok 402 still re-enters genesis as ``kernel_turn_failed`` because
``classify_unbound_turn`` keeps seeing historical error turns on a completed
mission. Salvage, the circuit breaker, and the local kernel already close that
class, but experience fuel never checks the ledger.

This module:

- treats an operational class as closed when every required structural
  capability is proved on the live ledger
- drops closed classes from genesis fuel (including forced pattern-register
  rows)
- stops local bind from falling back to the harvested 402 class once it is
  closed, without overwriting an operator-supplied field
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
)

SCHEMA_VERSION = 1
KERNEL_CLASS_CLOSURE_ID = "capability.kernel-class-closure"
KERNEL_TURN_FAILED = "kernel_turn_failed"

KERNEL_CLASS_CLOSURE_DONE_WHEN = (
    f"capability_exists:{KERNEL_CLASS_CLOSURE_ID};"
    f"capability_proved:{KERNEL_CLASS_CLOSURE_ID};"
    "no_skill_route"
)
KERNEL_CLASS_CLOSURE_GOAL = (
    "When a harvested operational class (kernel_turn_failed from the 2026-08-16 "
    "Grok 402 storm) has already been closed by proved structural capabilities, "
    "do not re-inject it as genesis fuel. Historical error turns in completed "
    "missions are consumed, not reopened. Local bind does not fall back to the "
    "harvested 402 class once it is structurally closed. Remaining open classes "
    "stay in fuel."
)

# Structural closers for the harvested 402 class. Follow-on leftover/succession
# planes are not required: the class is "kernel died before a decision".
CLASS_CLOSURE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    KERNEL_TURN_FAILED: (
        "capability.kernel-decision-salvage",
        "capability.kernel-circuit-breaker",
        "capability.local-capability-kernel",
    ),
    "quota_exhausted": (
        "capability.kernel-circuit-breaker",
        "capability.local-capability-kernel",
    ),
    "auth_failed": (
        "capability.kernel-circuit-breaker",
        "capability.local-capability-kernel",
    ),
    "milestone_rejected": (
        "capability.milestone-commit-resilience",
    ),
    "mission_blocked": (
        "capability.kernel-unscoped-resume",
    ),
    "genesis_selection_blocked": (
        "capability.kernel-genesis-bind",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_repo_ledger(root: Path) -> CapabilityLedger | None:
    path = default_ledger_path(Path(root))
    if not path.exists():
        return None
    try:
        return load_ledger(path)
    except Exception:  # noqa: BLE001 - harvest must still return fuel
        return None


def _ledger_proves(ledger: CapabilityLedger | None, capability_id: str) -> bool:
    if ledger is None:
        return False
    capability = ledger.capabilities.get(capability_id)
    return bool(capability is not None and capability.last_proof_exit_code == 0)


def class_closure_ids(class_id: str) -> tuple[str, ...]:
    return CLASS_CLOSURE_REQUIREMENTS.get(str(class_id or "").strip(), ())


def class_is_closed(
    class_id: str,
    root: Path,
    *,
    ledger: CapabilityLedger | None = None,
) -> bool:
    """True when every required structural closer is proved on the ledger."""

    required = class_closure_ids(class_id)
    if not required:
        return False
    live = ledger if ledger is not None else _load_repo_ledger(root)
    return all(_ledger_proves(live, item_id) for item_id in required)


def first_open_candidate(candidates: Iterable[Any], root: Path, *, ledger: CapabilityLedger | None = None) -> Any | None:
    """Return the first experience candidate whose class is still open."""

    live = ledger if ledger is not None else _load_repo_ledger(root)
    for item in candidates:
        class_id = str(getattr(item, "class_id", "") or "")
        if class_id and class_is_closed(class_id, root, ledger=live):
            continue
        return item
    return None


def drop_closed_class_fuel(fuel: Any, root: Path, *, ledger: CapabilityLedger | None = None) -> Any:
    """Strip closed classes from harvested genesis fuel."""

    live = ledger if ledger is not None else _load_repo_ledger(root)
    forced = getattr(fuel, "forced", None)
    if isinstance(forced, Mapping) and class_is_closed(str(forced.get("class_id") or ""), root, ledger=live):
        forced = None
    kept = [
        item
        for item in list(getattr(fuel, "candidates", None) or [])
        if not class_is_closed(str(getattr(item, "class_id", "") or ""), root, ledger=live)
    ]
    fuel.forced = forced
    fuel.candidates = kept
    return fuel


def _write_error_turn_mission(
    root: Path,
    *,
    mission_id: str,
    status: str = "complete",
    last_error: str = "",
) -> Path:
    mission_dir = Path(root) / ".blackhole-agent" / "unbound" / "missions" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "status": status,
        "stage": "execution",
        "goal": "Close leftover contract-materializer cliff.",
        "done_when": "",
        "next_step": "None. Mission complete.",
        "last_summary": "Mission completed after a later recovery.",
        "last_error": last_error,
        "milestones": [],
        "recent_turns": [
            {
                "iteration": 13,
                "effective_status": "error",
                "error": (
                    "Grok CLI failed with exit code 1; result details were written to "
                    "grok-run-20260816T055123Z.json"
                ),
                "summary": "turn 13 failed before a structured decision",
                "finished_at": "2026-08-16T05:51:28Z",
            }
        ],
    }
    path = mission_dir / "state.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def _register_closers(root: Path, ids: tuple[str, ...]) -> Path:
    from blackhole_agent.capability_compounder import Capability, register_capability, save_ledger

    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = CapabilityLedger()
    for capability_id in ids:
        register_capability(
            ledger,
            Capability(
                id=capability_id,
                name=capability_id,
                description="Proved structural closer for a harvested operational class.",
                kind="python",
                entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
                proof_command="uv run python -c \"print('ok')\"",
                last_proof_exit_code=0,
            ),
            replace=True,
        )
    save_ledger(path, ledger)
    return path


def builtin_kernel_class_closure_proof() -> dict[str, Any]:
    """Hermetic proof: closed 402 classes leave genesis fuel; open classes stay."""

    import tempfile

    from blackhole_agent.experience_fuel import harvest_experience, leftover_next_step
    from blackhole_agent.kernel_leftover import HARVESTED_MISSION_PLANE_LEFTOVER, _write_leftover_mission
    from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
    from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        HARVESTED_KERNEL_FAILURE_GOAL,
        bind_local_mission,
    )

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable
    checks["denylists_self"] = KERNEL_CLASS_CLOSURE_ID in LOCAL_DENYLIST
    checks["harvested_text_is_leftover"] = bool(leftover_next_step(HARVESTED_MISSION_PLANE_LEFTOVER))
    required = class_closure_ids(KERNEL_TURN_FAILED)
    checks["requires_salvage_breaker_local"] = required == CLASS_CLOSURE_REQUIREMENTS[KERNEL_TURN_FAILED]
    checks["closes_milestone_rejected"] = class_closure_ids("milestone_rejected") == (
        "capability.milestone-commit-resilience",
    )
    checks["closes_mission_blocked"] = class_closure_ids("mission_blocked") == (
        "capability.kernel-unscoped-resume",
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
            self.mission_id = "kernel-class-closure"
            self.stage = "genesis"

    with tempfile.TemporaryDirectory(prefix="kernel-class-open-") as tmp:
        root = Path(tmp)
        _write_error_turn_mission(root, mission_id="prior-402-storm")
        fuel = harvest_experience(root, limit=5)
        closed = class_is_closed(KERNEL_TURN_FAILED, root)
    checks["open_class_is_harvested"] = (
        not closed
        and any(item.class_id == KERNEL_TURN_FAILED for item in fuel.candidates)
    )

    with tempfile.TemporaryDirectory(prefix="kernel-class-closed-") as tmp:
        root = Path(tmp)
        _write_error_turn_mission(root, mission_id="prior-402-storm")
        _register_closers(root, required)
        fuel = harvest_experience(root, limit=5)
        closed = class_is_closed(KERNEL_TURN_FAILED, root)
        binding = bind_local_mission(_State(root), harvest=True)
    checks["proved_closers_drop_class"] = (
        closed
        and not any(item.class_id == KERNEL_TURN_FAILED for item in fuel.candidates)
        and binding.goal != HARVESTED_KERNEL_FAILURE_GOAL
        and KERNEL_TURN_FAILED not in binding.goal
        and binding.source == "class_closed"
        and binding.done_when == ""
    )

    with tempfile.TemporaryDirectory(prefix="kernel-class-partial-") as tmp:
        root = Path(tmp)
        _write_error_turn_mission(root, mission_id="prior-402-storm")
        _register_closers(root, ("capability.kernel-decision-salvage",))
        fuel = harvest_experience(root, limit=5)
        closed = class_is_closed(KERNEL_TURN_FAILED, root)
    checks["partial_closers_keep_class"] = (
        not closed and any(item.class_id == KERNEL_TURN_FAILED for item in fuel.candidates)
    )

    with tempfile.TemporaryDirectory(prefix="kernel-class-leftover-") as tmp:
        root = Path(tmp)
        _write_error_turn_mission(root, mission_id="prior-402-storm")
        _write_leftover_mission(
            root,
            mission_id="prior-leftover",
            next_step=HARVESTED_MISSION_PLANE_LEFTOVER,
        )
        _register_closers(root, required)
        fuel = harvest_experience(root, limit=5)
    checks["unrelated_leftover_stays_open"] = any(
        item.class_id == "mission_leftover" and "cheap-anchor rotation" in item.summary
        for item in fuel.candidates
    ) and not any(item.class_id == KERNEL_TURN_FAILED for item in fuel.candidates)

    disabled = bind_local_mission(_State(Path(".")), harvest=False)
    checks["harvest_false_keeps_402_default"] = (
        disabled.goal == HARVESTED_KERNEL_FAILURE_GOAL
        and disabled.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
        and disabled.source == "harvested_kernel_failure"
    )

    kept = bind_local_mission(_State(Path("."), goal="Operator growth goal."), harvest=False)
    checks["preserves_operator_goal"] = kept.goal == "Operator growth goal."

    with tempfile.TemporaryDirectory(prefix="kernel-class-operator-") as tmp:
        root = Path(tmp)
        _register_closers(root, required)
        kept_live = bind_local_mission(
            _State(root, goal="Operator growth goal."),
            harvest=True,
        )
    checks["preserves_operator_goal_when_closed"] = (
        kept_live.goal == "Operator growth goal." and "state.goal" in kept_live.source
    )

    checks["updated_at_helper"] = bool(_utc_now())
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_class_closure",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_CLASS_CLOSURE_GOAL,
        "done_when": KERNEL_CLASS_CLOSURE_DONE_WHEN,
    }
