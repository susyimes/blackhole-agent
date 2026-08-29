"""Resume a recovered first-class kernel from the local-campaign handoff.

The harvested 402 stack salvages a decision, trips a breaker, fails over to
a local kernel, and binds a campaign. That campaign was written to the
mission worktree (where the ledger lives) and only advertised as prompt
text from the durable repo. After worktree GC — or when a new genesis
starts — the recovered kernel invents a mission instead of resuming.

This module makes resume mechanical: unfinished campaign fields fill empty
genesis, stage flips to execution, and the campaign is persisted on the
durable repo_path so it survives worktree reclamation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import legacy_pipeline_was_used
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    durable_campaign_root,
    load_campaign,
    save_campaign,
)

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


KERNEL_RESUME_DONE_WHEN = (
    "capability_exists:capability.kernel-resume;"
    "capability_proved:capability.kernel-resume;"
    "no_skill_route"
)


def _continue_resumed_follow_ons(state: Any, durable: Path) -> None:
    """Attach remaining succession, then a bounded mission-plane, without failing resume."""

    try:
        from blackhole_agent.kernel_succession import continue_resumed_succession

        continue_resumed_succession(state, repo_path=durable)
    except Exception:  # noqa: BLE001 - resume must still return bound fields
        pass
    try:
        from blackhole_agent.kernel_mission_plane import continue_resumed_mission_plane

        continue_resumed_mission_plane(state, repo_path=durable)
    except Exception:  # noqa: BLE001 - resume must still return bound fields
        pass


def campaign_is_resumable(campaign: LocalCampaign) -> bool:
    if int(campaign.tick_count or 0) <= 0:
        return False
    if str(campaign.consumed_at or "").strip():
        return False
    if campaign.last_contract_met is True:
        return False
    if str(campaign.goal or "").strip() and str(campaign.done_when or "").strip():
        return True
    try:
        from blackhole_agent.kernel_unscoped_resume import campaign_has_unscoped_remaining

        return campaign_has_unscoped_remaining(campaign)
    except Exception:  # noqa: BLE001 - resume must still fail closed
        return False


def _scope_campaign_for_resume(campaign: LocalCampaign) -> bool:
    """Fill empty campaign fields from remaining program steps when present."""

    try:
        from blackhole_agent.kernel_unscoped_resume import scope_unscoped_campaign

        return scope_unscoped_campaign(campaign)
    except Exception:  # noqa: BLE001 - resume must still copy existing fields
        return bool(str(campaign.goal or "").strip() and str(campaign.done_when or "").strip())


def bind_create_fields(
    repo_path: Path,
    goal: str = "",
    done_when: str = "",
    *,
    lineage_ref: str = "",
) -> tuple[str, str, str]:
    """Fill missing create_mission fields from an unfinished local campaign."""

    filled_goal = str(goal or "").strip()
    filled_done = str(done_when or "").strip()
    if filled_goal and filled_done:
        return filled_goal, filled_done, "operator"
    campaign = load_campaign(Path(repo_path))
    scoped = _scope_campaign_for_resume(campaign)
    if not campaign_is_resumable(campaign):
        try:
            from blackhole_agent.kernel_genesis_bind import bind_gate_passing_successor

            succ_goal, succ_done, succ_source = bind_gate_passing_successor(
                Path(repo_path),
                campaign=campaign,
                lineage_ref=lineage_ref,
            )
        except Exception:  # noqa: BLE001 - create bind must still fail closed
            succ_goal, succ_done, succ_source = "", "", ""
        if succ_source:
            if not filled_goal:
                filled_goal = succ_goal
            if not filled_done:
                filled_done = succ_done
            return filled_goal, filled_done, succ_source
        return filled_goal, filled_done, ""
    if scoped:
        save_campaign(Path(repo_path), campaign)
    if not filled_goal:
        filled_goal = campaign.goal
    if not filled_done:
        filled_done = campaign.done_when
    return filled_goal, filled_done, "local_campaign"


def hydrate_mission_from_campaign(
    state: Any,
    repo_path: Path | None = None,
    *,
    persist: bool = False,
) -> dict[str, Any]:
    """Adopt an unfinished campaign into empty genesis fields. Operator fields stay."""

    durable = Path(repo_path) if repo_path is not None else durable_campaign_root(state)
    campaign = load_campaign(durable)
    scoped = _scope_campaign_for_resume(campaign)
    before_goal = str(getattr(state, "goal", "") or "").strip()
    before_done = str(getattr(state, "done_when", "") or "").strip()
    if before_goal and before_done:
        if str(getattr(state, "stage", "") or "") == "genesis":
            state.stage = "execution"
        _continue_resumed_follow_ons(state, durable)
        return {
            "applied": False,
            "source": "state",
            "reason": "already_bound",
            "goal": before_goal,
            "done_when": before_done,
            "stage": str(getattr(state, "stage", "") or ""),
        }
    if not campaign_is_resumable(campaign):
        try:
            from blackhole_agent.kernel_genesis_bind import bind_gate_passing_successor

            succ_goal, succ_done, succ_source = bind_gate_passing_successor(
                durable,
                campaign=campaign,
            )
        except Exception:  # noqa: BLE001 - hydrate must still fail closed
            succ_goal, succ_done, succ_source = "", "", ""
        if succ_source:
            applied = False
            if not before_goal:
                state.goal = succ_goal
                applied = True
            if not before_done:
                state.done_when = succ_done
                applied = True
            if str(getattr(state, "goal", "") or "").strip() and str(
                getattr(state, "done_when", "") or ""
            ).strip():
                state.stage = "execution"
            return {
                "applied": applied,
                "source": succ_source,
                "reason": "genesis_bind",
                "goal": str(getattr(state, "goal", "") or ""),
                "done_when": str(getattr(state, "done_when", "") or ""),
                "stage": str(getattr(state, "stage", "") or ""),
            }
        return {
            "applied": False,
            "source": "",
            "reason": "no_resumable_campaign",
            "goal": before_goal,
            "done_when": before_done,
            "stage": str(getattr(state, "stage", "") or ""),
        }
    applied = False
    if not before_goal:
        state.goal = campaign.goal
        applied = True
    if not before_done:
        state.done_when = campaign.done_when
        applied = True
    if str(getattr(state, "goal", "") or "").strip() and str(getattr(state, "done_when", "") or "").strip():
        state.stage = "execution"
    mission_id = str(getattr(state, "mission_id", "") or "")
    if persist and (applied or scoped) and mission_id:
        if campaign.resumed_by_mission_id != mission_id:
            campaign.resumed_by_mission_id = mission_id
        save_campaign(durable, campaign)
    _continue_resumed_follow_ons(state, durable)
    return {
        "applied": applied,
        "source": "local_campaign",
        "reason": "hydrated",
        "goal": str(getattr(state, "goal", "") or ""),
        "done_when": str(getattr(state, "done_when", "") or ""),
        "stage": str(getattr(state, "stage", "") or ""),
    }


def consume_resumed_campaign(state: Any, repo_path: Path | None = None) -> bool:
    """Mark a campaign consumed so a later genesis cannot rebind finished work."""

    durable = Path(repo_path) if repo_path is not None else durable_campaign_root(state)
    campaign = load_campaign(durable)
    if not campaign.tick_count or campaign.consumed_at:
        return False
    goal = str(getattr(state, "goal", "") or "")
    mission_id = str(getattr(state, "mission_id", "") or "")
    claimed = campaign.resumed_by_mission_id in {"", mission_id} or campaign.goal == goal
    if not claimed:
        return False
    campaign.consumed_at = _utc_now()
    save_campaign(durable, campaign)
    return True


def builtin_kernel_resume_proof() -> dict[str, Any]:
    """Hermetic proof: a recovered kernel resumes the durable campaign, not genesis."""

    import json
    import tempfile

    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        HARVESTED_KERNEL_FAILURE_GOAL,
        _write_fixture_ledger,
        campaign_path,
        render_local_campaign_for_prompt,
    )
    from blackhole_agent.unbound import UnboundMission, build_turn_prompt

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable

    class _State:
        def __init__(
            self,
            repo: Path,
            workspace: Path | None = None,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-resume",
            stage: str = "genesis",
        ) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(workspace or repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = mission_id
            self.stage = stage

    unfinished = LocalCampaign(
        mission_id="prior",
        goal="Keep growing after a 402.",
        done_when="capability_exists:repo.import-health;no_skill_route",
        bound_from="harvested_kernel_failure",
        tick_count=2,
        completed_ids=["capability.fixture-local-a"],
        last_contract_met=False,
        last_summary="local campaign advanced",
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-hydrate-") as tmp:
        root = Path(tmp)
        save_campaign(root, unfinished)
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        reloaded = load_campaign(root)
    checks["unfinished_campaign_hydrates_empty_genesis"] = (
        report["applied"] is True
        and empty.goal == unfinished.goal
        and empty.done_when == unfinished.done_when
        and empty.stage == "execution"
        and reloaded.resumed_by_mission_id == "mission-resume"
    )

    keep_goal = _State(Path("."), goal="Operator goal")
    save_target = Path(".")
    keep_report = hydrate_mission_from_campaign(keep_goal, repo_path=save_target)
    checks["preserves_operator_goal"] = keep_goal.goal == "Operator goal"

    with tempfile.TemporaryDirectory(prefix="kernel-resume-keep-done-") as tmp:
        root = Path(tmp)
        save_campaign(root, unfinished)
        keep_done = _State(root, done_when="capability_exists:repo.import-health")
        hydrate_mission_from_campaign(keep_done)
    checks["preserves_operator_done_when"] = (
        keep_done.done_when == "capability_exists:repo.import-health"
        and keep_done.goal == unfinished.goal
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-finished-") as tmp:
        root = Path(tmp)
        finished = LocalCampaign(
            mission_id="done",
            goal=unfinished.goal,
            done_when=unfinished.done_when,
            tick_count=3,
            last_contract_met=True,
        )
        save_campaign(root, finished)
        skipped = _State(root)
        skip_report = hydrate_mission_from_campaign(skipped)
    checks["finished_campaign_binds_successor"] = (
        skip_report["applied"] is True
        and skipped.stage == "execution"
        and bool(skipped.goal)
        and str(skip_report.get("source") or "").startswith("genesis_bind")
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-durable-") as tmp:
        durable = Path(tmp) / "repo"
        worktree = Path(tmp) / "worktree"
        durable.mkdir()
        worktree.mkdir()
        _write_fixture_ledger(worktree)
        split = _State(durable, worktree, goal="Keep growing after a 402.", done_when="A structured decision is recorded.")

        def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-grok-run.json").write_text(
                json.dumps(HARVESTED_GROK_402),
                encoding="utf-8",
            )
            raise RuntimeError("Grok CLI failed with exit code 1; Payment Required usage balance exhausted")

        execute_kernel_turn_with_salvage(
            split,
            "prompt",
            worktree / "turn",
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
        durable_campaign = load_campaign(durable)
        worktree_campaign = load_campaign(worktree)
        handoff = render_local_campaign_for_prompt(durable)
    checks["durable_tick_writes_repo_not_only_worktree"] = (
        durable_campaign.tick_count >= 1
        and durable_campaign.goal == "Keep growing after a 402."
        and worktree_campaign.tick_count == 0
        and "Local-kernel campaign handoff" in handoff
        and not campaign_path(worktree).is_file()
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-prompt-") as tmp:
        root = Path(tmp)
        save_campaign(root, unfinished)
        mission = UnboundMission(
            schema_version=1,
            mission_id="mission-resume",
            created_at="2026-08-17T00:00:00Z",
            updated_at="2026-08-17T00:00:00Z",
            repo_path=str(root),
            workspace_path=str(root),
            branch="unbound/test",
            target_branch="main",
            goal="",
            done_when="",
            stage="genesis",
            base_head="abc",
            last_milestone_head="abc",
        )
        prompt = build_turn_prompt(
            mission,
            {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"},
            state_path=root / "state.json",
        )
    checks["prompt_skips_genesis_after_hydrate"] = (
        "Mission genesis is still open" not in prompt
        and "Keep growing after a 402." in prompt
        and "Local-kernel campaign handoff" in prompt
        and mission.stage == "execution"
    )

    create_goal, create_done, create_source = bind_create_fields(Path("."), "Operator", "already")
    checks["create_bind_keeps_operator"] = (
        create_goal == "Operator" and create_done == "already" and create_source == "operator"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-create-") as tmp:
        root = Path(tmp)
        save_campaign(root, unfinished)
        bound_goal, bound_done, bound_source = bind_create_fields(root)
    checks["create_bind_uses_campaign"] = (
        bound_goal == unfinished.goal
        and bound_done == unfinished.done_when
        and bound_source == "local_campaign"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-402-") as tmp:
        durable = Path(tmp) / "repo"
        worktree = Path(tmp) / "worktree"
        durable.mkdir()
        worktree.mkdir()
        _write_fixture_ledger(worktree)
        genesis = _State(durable, worktree)
        execute_kernel_turn_with_salvage(
            genesis,
            "prompt",
            worktree / "turn-402",
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
        recovered = _State(durable, worktree, mission_id="recovered")
        recovered_report = hydrate_mission_from_campaign(recovered, persist=True)
        recovered_prompt = build_turn_prompt(
            UnboundMission(
                schema_version=1,
                mission_id="recovered",
                created_at="2026-08-17T00:00:00Z",
                updated_at="2026-08-17T00:00:00Z",
                repo_path=str(durable),
                workspace_path=str(worktree),
                branch="unbound/test",
                target_branch="main",
                goal="",
                done_when="",
                stage="genesis",
                base_head="abc",
                last_milestone_head="abc",
            ),
            {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"},
            state_path=durable / "state.json",
        )
    checks["execute_402_then_fresh_genesis_resumes"] = (
        recovered_report["applied"] is True
        and recovered.stage == "execution"
        and recovered.goal == HARVESTED_KERNEL_FAILURE_GOAL
        and recovered.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
        and "Mission genesis is still open" not in recovered_prompt
        and HARVESTED_KERNEL_FAILURE_GOAL in recovered_prompt
    )

    with tempfile.TemporaryDirectory(prefix="kernel-resume-consume-") as tmp:
        root = Path(tmp)
        save_campaign(root, unfinished)
        adopted = _State(root)
        hydrate_mission_from_campaign(adopted, persist=True)
        consumed = consume_resumed_campaign(adopted)
        after = _State(root, mission_id="later")
        blocked = hydrate_mission_from_campaign(after)
    checks["consume_prevents_rebind"] = (
        consumed is True
        and blocked["applied"] is True
        and after.goal != unfinished.goal
        and str(blocked.get("source") or "").startswith("genesis_bind")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_resume",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
