"""Sovereign local contract finality after a 402-class kernel death.

Cheap rotation, succession, and the mission-plane already produce in-process
progress and can mark ``mission_plane_ok``. Local ticks still emit
``status=continue`` even when that contract is machine-checkably met, so a
dead Grok cannot close a mission. The harvested leftover stack therefore
idles until a first-class kernel recovers.

This module finalizes only campaign-relative contracts (``mission_plane_ok``
or ``program_passes``) that the local campaign itself satisfied. Ledger-static
predicates such as ``capability_exists`` never complete a 402-local genesis
just because the durable ledger already contained them. The Unbound
controller accepts that complete without a git milestone commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import legacy_pipeline_was_used
from blackhole_agent.local_mission_sovereignty import LocalCampaign

CAMPAIGN_RELATIVE_KINDS = frozenset({"mission_plane_ok", "program_passes"})
KERNEL_FINALITY_DONE_WHEN = (
    "capability_exists:capability.kernel-finality;"
    "capability_proved:capability.kernel-finality;"
    "no_skill_route"
)
KERNEL_FINALITY_GOAL = (
    "When a 402-class kernel death leaves only the local sovereign stack, and "
    "that stack's bound contract is machine-checkably met by campaign progress "
    "(mission_plane_ok or program_passes), emit status=complete so Unbound can "
    "close the mission without waiting for a recovered first-class kernel."
)


def _decision_field(decision: Any, name: str, default: Any = "") -> Any:
    if isinstance(decision, Mapping):
        return decision.get(name, default)
    return getattr(decision, name, default)


def contract_has_campaign_progress(contract: Mapping[str, Any] | None) -> bool:
    """True when done_when includes a predicate the local campaign can satisfy."""

    for item in list((contract or {}).get("results") or []):
        if isinstance(item, Mapping) and str(item.get("kind") or "") in CAMPAIGN_RELATIVE_KINDS:
            return True
    return False


def can_finalize_local_campaign(
    contract: Mapping[str, Any] | None,
    campaign: Any,
    *,
    invoked_ok: bool = False,
) -> bool:
    """True when local ticks may emit complete instead of an idle continue."""

    payload = dict(contract or {})
    if payload.get("machine_checkable") is not True:
        return False
    if payload.get("met") is not True:
        return False
    if not contract_has_campaign_progress(payload):
        return False
    completed = [item for item in list(getattr(campaign, "completed_ids", None) or []) if item]
    if not completed and not invoked_ok:
        return False
    return True


def waive_git_milestone_for_local_finality(decision: Any, kernel: str) -> bool:
    """Local complete of a met contract does not require a git behavior milestone."""

    if str(kernel or "").strip().lower() != "local":
        return False
    if str(_decision_field(decision, "status") or "") != "complete":
        return False
    if not bool(_decision_field(decision, "done_when_met", False)):
        return False
    if not str(_decision_field(decision, "capability_delta") or "").strip():
        return False
    if not _decision_field(decision, "outcome_evidence", ()):
        return False
    return True


def builtin_kernel_finality_proof() -> dict[str, Any]:
    """Hermetic proof: 402-local ticks complete a met campaign contract."""

    import json
    import subprocess
    import tempfile

    from blackhole_agent.kernel_mission_plane import _write_mission_plane_ledger
    from blackhole_agent.kernel_resume import campaign_is_resumable, hydrate_mission_from_campaign
    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
    from blackhole_agent.capability_compounder import CapabilityLedger
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        HARVESTED_KERNEL_FAILURE_GOAL,
        _write_fixture_ledger,
        bind_local_mission,
        evaluate_campaign_contract,
        load_campaign,
        local_mission_tick,
        save_campaign,
    )
    from blackhole_agent.unbound import (
        KernelTurnResult,
        TurnDecision,
        UnboundMission,
        evaluate_milestone,
        git_head,
        load_mission,
        run_unbound_turn,
        save_mission,
    )

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable
    checks["denylists_self"] = "capability.kernel-finality" in LOCAL_DENYLIST

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "Keep growing after a 402.",
            done_when: str = "mission_plane_ok;no_skill_route",
            mission_id: str = "kernel-finality",
        ) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = mission_id
            self.stage = "execution"

    with tempfile.TemporaryDirectory(prefix="kernel-finality-plane-") as tmp:
        root = Path(tmp)
        _write_mission_plane_ledger(root)
        ticks = [local_mission_tick(_State(root), root) for _ in range(4)]
        fifth = local_mission_tick(_State(root), root)
        persisted = load_campaign(root)
        fourth = ticks[3]
    checks["plane_ticks_continue_until_contract"] = all(
        item.get("status") == "continue" for item in ticks[:3]
    )
    checks["plane_tick_completes_when_met"] = (
        fourth.get("status") == "complete"
        and fourth.get("done_when_met") is True
        and (fourth.get("contract") or {}).get("met") is True
        and bool(fourth.get("capability_delta"))
        and str(fourth.get("next_step") or "").lower().startswith("none")
        and bool((persisted.handoff or {}).get("local_finality"))
        and persisted.last_contract_met is True
    )
    checks["finalized_tick_stays_complete"] = (
        fifth.get("status") == "complete" and fifth.get("done_when_met") is True
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-static-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root, include_sovereignty=True)
        static = local_mission_tick(
            _State(root, goal=HARVESTED_KERNEL_FAILURE_GOAL, done_when=HARVESTED_KERNEL_FAILURE_DONE_WHEN),
            root,
        )
    checks["ledger_static_contract_does_not_complete"] = (
        static.get("status") == "continue"
        and static.get("done_when_met") is True
        and (static.get("contract") or {}).get("met") is True
        and can_finalize_local_campaign(static.get("contract") or {}, LocalCampaign(completed_ids=["x"]), invoked_ok=True)
        is False
    )

    free = evaluate_campaign_contract(CapabilityLedger(), "A structured decision is recorded.")
    checks["free_text_does_not_finalize"] = (
        free.get("machine_checkable") is False
        and can_finalize_local_campaign(free, LocalCampaign(completed_ids=["x"]), invoked_ok=True) is False
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-unsupported-") as tmp:
        root = Path(tmp)
        _write_mission_plane_ledger(root)
        blocked = None
        for _ in range(4):
            blocked = local_mission_tick(
                _State(root, done_when="mission_plane_ok;min_epochs:2"),
                root,
            )
    checks["unsupported_predicate_does_not_complete"] = (
        blocked is not None
        and blocked.get("status") == "continue"
        and (blocked.get("contract") or {}).get("met") is not True
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-program-") as tmp:
        root = Path(tmp)
        _write_mission_plane_ledger(root)
        program_tick = local_mission_tick(
            _State(root, done_when="program_passes:capability.fixture-local-a;no_skill_route"),
            root,
        )
    checks["program_passes_completes"] = (
        program_tick.get("status") == "complete"
        and program_tick.get("done_when_met") is True
        and (program_tick.get("invoked") or [{}])[0].get("capability_id") == "capability.fixture-local-a"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-empty-") as tmp:
        empty = local_mission_tick(_State(Path(tmp)), Path(tmp))
    checks["empty_ledger_continues"] = empty.get("status") == "continue" and empty.get("invoked") == []

    operator = _State(Path("."), goal="Operator growth goal.")
    kept = bind_local_mission(operator, harvest=False)
    checks["preserves_operator_goal"] = kept.goal == "Operator growth goal."

    def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-grok-run.json").write_text(
            json.dumps(HARVESTED_GROK_402),
            encoding="utf-8",
        )
        raise RuntimeError("Grok CLI failed with exit code 1; Payment Required usage balance exhausted")

    with tempfile.TemporaryDirectory(prefix="kernel-finality-402-") as tmp:
        repo = Path(tmp)
        _write_mission_plane_ledger(repo)
        state = _State(repo)
        last_decision: Any = None
        for name in ("turn-1", "turn-2", "turn-3", "turn-4"):
            state.kernel = "grok"
            _result, last_decision, last_meta = execute_kernel_turn_with_salvage(
                state,
                "prompt",
                repo / name,
                kernel_runner=boom,
                installed_kernels=set(),
                persist_health=False,
            )
        after = load_campaign(repo)
    checks["execute_402_then_complete"] = (
        last_decision.status == "complete"
        and last_decision.done_when_met is True
        and bool(last_decision.capability_delta)
        and last_meta.get("source") == "failover"
        and bool((after.handoff or {}).get("local_finality"))
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-resume-") as tmp:
        root = Path(tmp)
        finished = LocalCampaign(
            mission_id="prior",
            goal="Keep growing after a 402.",
            done_when="mission_plane_ok;no_skill_route",
            bound_from="harvested_kernel_failure",
            program=["capability.fixture-mission-plane-d"],
            cursor=1,
            completed_ids=["capability.fixture-mission-plane-d"],
            tick_count=4,
            last_contract_met=True,
            last_summary="finalized",
            handoff={"local_finality": True, "mission_plane_ok": True},
        )
        save_campaign(root, finished)
        recovered = _State(root, goal="", done_when="", mission_id="recovered")
        recovered.stage = "genesis"
        hydrate = hydrate_mission_from_campaign(recovered, persist=True)
    checks["finalized_campaign_is_not_resumable"] = campaign_is_resumable(finished) is False
    checks["finalized_campaign_binds_successor"] = (
        hydrate.get("applied") is True
        and bool(recovered.goal)
        and str(hydrate.get("source") or "").startswith("genesis_bind")
    )

    payload = {
        "status": "complete",
        "summary": "Local contract finality closed the mission.",
        "strategy": "Close locally after 402.",
        "next_step": "None. Mission complete.",
        "capability_delta": "Local kernel finalized a machine-checkable campaign contract.",
        "outcome_evidence": ["reason=local_finality", "contract_met=True"],
        "validation": [],
        "done_when_met": True,
        "mission_goal": KERNEL_FINALITY_GOAL,
        "done_when": "mission_plane_ok;no_skill_route",
    }
    complete_decision = TurnDecision.from_payload(payload)
    grok_gate = evaluate_milestone(complete_decision, changed_paths=[], kernel="grok")
    local_gate = evaluate_milestone(complete_decision, changed_paths=[], kernel="local")
    empty_delta = TurnDecision.from_payload({**payload, "capability_delta": ""})
    no_delta_gate = evaluate_milestone(empty_delta, changed_paths=[], kernel="local")
    checks["controller_rejects_grok_complete_without_git"] = grok_gate.accepted is False
    checks["controller_accepts_local_complete_without_git"] = local_gate.accepted is True
    checks["controller_rejects_local_complete_without_delta"] = no_delta_gate.accepted is False
    checks["waive_helper_matches_gate"] = (
        waive_git_milestone_for_local_finality(complete_decision, "local") is True
        and waive_git_milestone_for_local_finality(complete_decision, "grok") is False
    )

    with tempfile.TemporaryDirectory(prefix="kernel-finality-turn-") as tmp:
        repo = Path(tmp)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=repo, check=True)
        (repo / "src").mkdir()
        (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True)
        head = git_head(repo)
        state_path = repo / ".blackhole-agent" / "unbound" / "missions" / "finality" / "state.json"
        save_mission(
            state_path,
            UnboundMission(
                schema_version=1,
                mission_id="finality",
                created_at="2026-08-23T00:00:00Z",
                updated_at="2026-08-23T00:00:00Z",
                repo_path=str(repo),
                workspace_path=str(repo),
                branch="unbound/finality",
                target_branch="main",
                goal=KERNEL_FINALITY_GOAL,
                done_when="mission_plane_ok;no_skill_route",
                status="active",
                stage="execution",
                base_head=head,
                last_milestone_head=head,
                kernel="grok",
            ),
        )

        def local_complete_kernel(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> KernelTurnResult:
            return KernelTurnResult(
                kernel="local",
                last_message=json.dumps(payload),
                session_id="local",
                command=("local-capability-kernel",),
                result_path=str(Path(turn_dir) / "kernel" / "latest-local-run.json"),
            )

        record = run_unbound_turn(state_path, kernel_runner=local_complete_kernel)
        closed = load_mission(state_path)
        after_head = git_head(repo)
    checks["controller_closes_without_commit"] = (
        record.get("effective_status") == "complete"
        and record.get("requested_status") == "complete"
        and closed.status == "complete"
        and after_head == head
        and closed.milestone_count == 0
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_finality",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
