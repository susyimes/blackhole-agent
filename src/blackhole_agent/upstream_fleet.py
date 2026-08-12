"""Upstream fleet plane: impact-driven multi-target stewardship direction.

Control flow is owned by :mod:`blackhole_agent.upstream_stage_engine`
(``STAGE_ENGINE=True``, dialect ``fleet``). This module keeps stage domain
runners (inventory / portfolio / rank / dispatch) and fleet-specific seal
hooks; the ordered short-circuit pipeline, abort policy, and engine
annotations are shared with campaign.

The campaign plane (``upstream_campaign``) orchestrates a full loop for *one*
stewardship target. The impact plane (``upstream_impact``) measures post-
publication outcomes and can roll them into a portfolio. Neither decides what
to do *next* across the whole stewardship fleet.

The fleet plane closes that gap via engine-owned stages:

1. **inventory** — scan stewardship targets for defect readiness
   (patch-bound, pending-patch, empty, published-already);
2. **portfolio** — re-use a sealed impact portfolio or assess one through an
   injected portfolio seam (default: ``assess_impact_portfolio``);
3. **rank** — convert measured outcomes + inventory into ranked next actions:

   - ``rework_closed_unmerged`` — PR closed without merge (highest urgency)
   - ``rework_diverged`` — open PR whose head diverged from the sealed receipt
   - ``rework_pr_missing`` — publication receipt no longer resolves upstream
   - ``campaign_patch_bound`` — ready defects with no successful merge/release
   - ``bind_pending_patch`` — admitted findings still waiting for a patch
   - ``discover_empty`` — onboarded targets with no defects yet
   - ``follow_open`` — open PR still tracking; monitor, do not re-campaign
   - ``done_merged`` / ``done_released`` — terminal successes (no action)

4. **dispatch** (optional) — run the top-ranked campaignable action through the
   campaign plane with injected hermetic seams for proofs;
5. **seal** — write a fleet plan under ``artifacts/upstream-fleet/`` with
   sha256 digests of inventory, portfolio, ranked actions, and any dispatched
   campaign receipts; ``verify_fleet_plan`` re-checks the chain and detects
   tampering.

No skill-route discovery is used. The plane is direction, not a sixth
independent verifier of individual repairs — each action delegates to existing
planes through seams.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent import upstream_campaign as ucamp
from blackhole_agent import upstream_impact as ui
from blackhole_agent import upstream_repair as ur
from blackhole_agent import upstream_stage_engine as se
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

# Owned by the multi-stage durable pipeline engine (not a hand-wired stage chain).
STAGE_ENGINE = True
STAGE_ENGINE_DIALECT = "fleet"

# Multi-mode control engine owns pipeline control flow.
CONTROL_ENGINE = True
CONTROL_ENGINE_MODE = "pipeline"

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-fleet"
STEWARDSHIP_ROOT = REPO_ROOT / "stewardship"

# Keep stage vocabulary aligned with the engine dialect registration.
assert frozenset(se.FLEET_STAGES) == se.get_pipeline_dialect("fleet").valid_stages

# Lower rank_score = higher urgency. Terminal "done_*" / "follow_*" sit at the bottom.
ACTION_PRIORITY: dict[str, int] = {
    "rework_closed_unmerged": 10,
    "rework_diverged": 20,
    "rework_pr_missing": 30,
    "campaign_patch_bound": 40,
    "bind_pending_patch": 50,
    "discover_empty": 60,
    "follow_open": 80,
    "done_merged": 90,
    "done_released": 100,
}

# Actions that can be handed to the campaign plane as a dispatch.
CAMPAIGNABLE_ACTIONS = frozenset({
    "rework_closed_unmerged",
    "rework_diverged",
    "rework_pr_missing",
    "campaign_patch_bound",
    "discover_empty",
})

# Outcomes that mean the outward contribution already landed (no re-campaign).
TERMINAL_SUCCESS_OUTCOMES = frozenset({
    "impact_merged",
    "impact_released",
})

# Outcomes that demand rework rather than re-discovery.
REWORK_OUTCOMES: dict[str, str] = {
    "impact_closed_unmerged": "rework_closed_unmerged",
    "impact_open_diverged": "rework_diverged",
    "impact_pr_missing": "rework_pr_missing",
}


class FleetRefused(Exception):
    """A verdict-bearing refusal: the fleet plan must not continue."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


# ---------------------------------------------------------------------------
# digests / io


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(durable_read_path(path).read_bytes())


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(canonical.encode("utf-8"))


# ---------------------------------------------------------------------------
# inventory


def inventory_targets(
    stewardship_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Scan stewardship targets for defect readiness (no network)."""
    root = Path(stewardship_root) if stewardship_root is not None else STEWARDSHIP_ROOT
    if not root.is_dir():
        return []

    inventory: list[dict[str, Any]] = []
    for target_dir in ur.discover_targets(root):
        try:
            manifest = json.loads(
                durable_read_path(target_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        defects = list(manifest.get("defects") or [])
        patch_bound: list[str] = []
        pending_patch: list[str] = []
        for d in defects:
            did = str(d.get("id") or "")
            if not did:
                continue
            if d.get("pending_patch") or not d.get("patch"):
                pending_patch.append(did)
            else:
                patch_bound.append(did)
        entry = {
            "target_dir": str(target_dir),
            "name": str(manifest.get("name") or target_dir.name),
            "version": str(manifest.get("version") or ""),
            "slug": f"{manifest.get('name')}-{manifest.get('version')}",
            "upstream_repo": str(manifest.get("upstream_repo") or ""),
            "defect_count": len(defects),
            "patch_bound_ids": patch_bound,
            "pending_patch_ids": pending_patch,
            "empty": len(defects) == 0,
            "runtime": str(
                (manifest.get("driver") or {}).get("runtime")
                or manifest.get("runtime")
                or "python"
            ),
        }
        inventory.append(entry)
    inventory.sort(key=lambda e: (e.get("name") or "", e.get("version") or ""))
    return inventory


def _inventory_digest_payload(inventory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": e.get("name"),
            "version": e.get("version"),
            "defect_count": e.get("defect_count"),
            "patch_bound_ids": list(e.get("patch_bound_ids") or []),
            "pending_patch_ids": list(e.get("pending_patch_ids") or []),
            "empty": e.get("empty"),
            "runtime": e.get("runtime"),
        }
        for e in inventory
    ]


# ---------------------------------------------------------------------------
# ranking


def _portfolio_entries(portfolio: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not portfolio:
        return []
    return [dict(e) for e in (portfolio.get("entries") or []) if isinstance(e, Mapping)]


def _latest_outcome_by_defect(
    entries: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Map (name, version, defect_id) -> newest portfolio entry."""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in entries:
        key = (
            str(e.get("name") or ""),
            str(e.get("version") or ""),
            str(e.get("defect_id") or ""),
        )
        # Prefer entries that carry an impact_digest as "newer" when ties.
        prev = best.get(key)
        if prev is None:
            best[key] = dict(e)
            continue
        # Stable: keep first unless the new one has an outcome and prev doesn't.
        if not prev.get("outcome") and e.get("outcome"):
            best[key] = dict(e)
    return best


def rank_fleet_actions(
    inventory: Sequence[Mapping[str, Any]],
    portfolio: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank next actions from inventory + optional impact portfolio."""
    outcomes = _latest_outcome_by_defect(_portfolio_entries(portfolio))
    actions: list[dict[str, Any]] = []

    # 1) Outcome-driven actions for every portfolio entry that maps to a known target.
    inventory_by_nv: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(t.get("name") or ""), str(t.get("version") or "")): t for t in inventory
    }
    covered_defects: set[tuple[str, str, str]] = set()

    for key, entry in outcomes.items():
        name, version, defect_id = key
        covered_defects.add(key)
        outcome = str(entry.get("outcome") or "")
        target = inventory_by_nv.get((name, version))
        target_dir = str(target.get("target_dir") or "") if target else ""
        base = {
            "name": name,
            "version": version,
            "defect_id": defect_id,
            "target_dir": target_dir,
            "outcome": outcome,
            "pr_number": entry.get("pr_number"),
            "pr_url": entry.get("pr_url"),
            "impact_digest": entry.get("impact_digest"),
            "source": "portfolio",
        }
        if outcome in TERMINAL_SUCCESS_OUTCOMES:
            action = "done_released" if outcome == "impact_released" else "done_merged"
            actions.append({
                **base,
                "action": action,
                "campaignable": False,
                "priority": ACTION_PRIORITY[action],
                "reason": f"portfolio outcome {outcome} is terminal",
            })
        elif outcome == "impact_open":
            actions.append({
                **base,
                "action": "follow_open",
                "campaignable": False,
                "priority": ACTION_PRIORITY["follow_open"],
                "reason": "PR still open; monitor, do not re-campaign",
            })
        elif outcome in REWORK_OUTCOMES:
            action = REWORK_OUTCOMES[outcome]
            actions.append({
                **base,
                "action": action,
                "campaignable": True,
                "priority": ACTION_PRIORITY[action],
                "reason": f"portfolio outcome {outcome} requires rework",
                "suggested_stages": ["repair", "contribution", "publication"],
            })
        else:
            # Unknown outcome: surface as follow so it is not silent.
            actions.append({
                **base,
                "action": "follow_open",
                "campaignable": False,
                "priority": ACTION_PRIORITY["follow_open"],
                "reason": f"unrecognized outcome {outcome!r}; monitor",
            })

    # 2) Inventory-driven actions for defects / targets without terminal success.
    for target in inventory:
        name = str(target.get("name") or "")
        version = str(target.get("version") or "")
        target_dir = str(target.get("target_dir") or "")
        patch_bound = list(target.get("patch_bound_ids") or [])
        pending = list(target.get("pending_patch_ids") or [])

        if target.get("empty"):
            actions.append({
                "name": name,
                "version": version,
                "defect_id": None,
                "target_dir": target_dir,
                "outcome": None,
                "action": "discover_empty",
                "campaignable": True,
                "priority": ACTION_PRIORITY["discover_empty"],
                "reason": "target has no defects; run discovery→admit",
                "suggested_stages": ["discovery", "admit"],
                "source": "inventory",
            })
            continue

        for defect_id in patch_bound:
            key = (name, version, defect_id)
            prior = outcomes.get(key)
            if prior and str(prior.get("outcome") or "") in TERMINAL_SUCCESS_OUTCOMES:
                continue
            if prior and str(prior.get("outcome") or "") == "impact_open":
                # Already following via portfolio path.
                continue
            if prior and str(prior.get("outcome") or "") in REWORK_OUTCOMES:
                # Already ranked as rework.
                continue
            actions.append({
                "name": name,
                "version": version,
                "defect_id": defect_id,
                "target_dir": target_dir,
                "outcome": (prior or {}).get("outcome") if prior else None,
                "action": "campaign_patch_bound",
                "campaignable": True,
                "priority": ACTION_PRIORITY["campaign_patch_bound"],
                "reason": (
                    "patch-bound defect with no successful merge/release"
                    if not prior
                    else f"patch-bound defect still open under outcome {prior.get('outcome')}"
                ),
                "suggested_stages": ["repair", "contribution", "publication"],
                "source": "inventory",
            })

        for defect_id in pending:
            key = (name, version, defect_id)
            if key in covered_defects and outcomes.get(key):
                # Portfolio already ranked this id (unusual for pending).
                continue
            actions.append({
                "name": name,
                "version": version,
                "defect_id": defect_id,
                "target_dir": target_dir,
                "outcome": None,
                "action": "bind_pending_patch",
                "campaignable": False,
                "priority": ACTION_PRIORITY["bind_pending_patch"],
                "reason": "admitted finding awaiting patch binding",
                "source": "inventory",
            })

    actions.sort(
        key=lambda a: (
            int(a.get("priority") or 999),
            str(a.get("name") or ""),
            str(a.get("version") or ""),
            str(a.get("defect_id") or ""),
            str(a.get("action") or ""),
        )
    )
    # Assign stable rank positions (1-based).
    for i, action in enumerate(actions, start=1):
        action["rank"] = i
    return actions


def _actions_digest_payload(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": a.get("rank"),
            "action": a.get("action"),
            "name": a.get("name"),
            "version": a.get("version"),
            "defect_id": a.get("defect_id"),
            "priority": a.get("priority"),
            "campaignable": a.get("campaignable"),
            "outcome": a.get("outcome"),
            "impact_digest": a.get("impact_digest"),
            "source": a.get("source"),
        }
        for a in actions
    ]


# ---------------------------------------------------------------------------
# plan seal / verify


def _plan_digest_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": plan.get("schema_version"),
        "inventory_digest": plan.get("inventory_digest"),
        "portfolio_digest": plan.get("portfolio_digest"),
        "actions_digest": plan.get("actions_digest"),
        "action_count": plan.get("action_count"),
        "campaignable_count": plan.get("campaignable_count"),
        "dispatched_count": plan.get("dispatched_count"),
        "dispatch_digests": plan.get("dispatch_digests") or {},
        "ok": plan.get("ok"),
        "verdict": plan.get("verdict"),
    }


def _action_counts(actions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in actions:
        key = str(a.get("action") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def plan_fleet(
    *,
    stewardship_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    publication_root: Path | None = None,
    portfolio_runner: Callable[..., dict[str, Any]] | None = None,
    gh: Callable[..., str] | None = None,
    absorption_checker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    assess_portfolio: bool = False,
    dispatch: bool = False,
    dispatch_limit: int = 1,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    out_root: Path | None = None,
    stages: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build (and optionally dispatch) a sealed fleet plan.

    Control flow is owned by :mod:`upstream_stage_engine` (``STAGE_ENGINE``).
    Stage domain runners remain fleet-local hooks.

    Parameters
    ----------
    assess_portfolio:
        When True and no ``portfolio`` / ``portfolio_dir`` is given, call the
        impact portfolio seam (live by default; inject ``portfolio_runner`` for
        hermetic proofs).
    dispatch:
        When True, run up to ``dispatch_limit`` campaignable actions through
        ``campaign_runner`` (default: ``upstream_campaign.run_campaign``).
        Also appends the ``dispatch`` stage when ``stages`` is omitted.
    stages:
        Optional explicit stage list (subset of inventory/portfolio/rank/dispatch).
        Default is inventory→portfolio→rank, plus dispatch when ``dispatch=True``.
    """
    has_portfolio_input = (
        portfolio is not None or portfolio_dir is not None or bool(assess_portfolio)
    )
    if stages is None:
        stage_list: list[str] = ["inventory", "portfolio", "rank"]
        if dispatch:
            stage_list.append("dispatch")
    else:
        try:
            stage_list = se.normalize_stages("fleet", stages)
        except se.StageRefused as exc:
            raise FleetRefused(exc.verdict, exc.detail) from exc

    ctx: dict[str, Any] = {
        "stewardship_root": stewardship_root,
        "portfolio_in": dict(portfolio) if portfolio is not None else None,
        "portfolio_dir": Path(portfolio_dir) if portfolio_dir is not None else None,
        "publication_root": publication_root,
        "portfolio_runner": portfolio_runner,
        "gh": gh,
        "absorption_checker": absorption_checker,
        "assess_portfolio": bool(assess_portfolio),
        "has_portfolio_input": has_portfolio_input,
        "dispatch_enabled": bool(dispatch),
        "dispatch_limit": max(0, int(dispatch_limit)),
        "campaign_runner": campaign_runner,
        "out_root": out_root,
        "inventory": [],
        "resolved_portfolio": None,
        "portfolio_source": "none",
        "actions": [],
        "campaignable": [],
        "dispatches": [],
        "dispatch_digests": {},
    }

    def run_stage(state: se.PipelineState, name: str) -> dict[str, Any]:
        c = state.context
        if name == "inventory":
            inventory = inventory_targets(c.get("stewardship_root"))
            c["inventory"] = inventory
            if not inventory and not c.get("has_portfolio_input"):
                # Preserve historical refuse-before-seal semantics.
                raise FleetRefused(
                    "fleet_empty",
                    "no stewardship targets and no portfolio supplied",
                )
            return {
                "stage": "inventory",
                "ok": True,
                "verdict": "inventoried",
                "inventory_count": len(inventory),
            }
        if name == "portfolio":
            resolved_portfolio: dict[str, Any] | None = None
            portfolio_source = "none"
            portfolio_in = c.get("portfolio_in")
            portfolio_dir_in = c.get("portfolio_dir")
            if portfolio_in is not None:
                resolved_portfolio = dict(portfolio_in)
                portfolio_source = "injected"
            elif portfolio_dir_in is not None:
                path = durable_read_path(Path(portfolio_dir_in) / "portfolio.json")
                if not path.is_file():
                    raise FleetRefused(
                        "portfolio_missing",
                        f"no portfolio.json under {portfolio_dir_in}",
                    )
                resolved_portfolio = json.loads(path.read_text(encoding="utf-8"))
                portfolio_source = "dir"
                checked = ui.verify_impact_portfolio(Path(portfolio_dir_in))
                if not checked.get("ok"):
                    raise FleetRefused(
                        "portfolio_unsealed",
                        f"portfolio seal failed: {checked.get('mismatched')}",
                    )
            elif c.get("assess_portfolio"):
                runner = c.get("portfolio_runner") or ui.assess_impact_portfolio
                result = runner(
                    publication_root=c.get("publication_root"),
                    gh=c.get("gh"),
                    absorption_checker=c.get("absorption_checker"),
                )
                pdir = result.get("portfolio_dir")
                if pdir and (Path(pdir) / "portfolio.json").is_file():
                    resolved_portfolio = json.loads(
                        (Path(pdir) / "portfolio.json").read_text(encoding="utf-8")
                    )
                    portfolio_source = "assessed"
                else:
                    resolved_portfolio = {
                        "schema_version": SCHEMA_VERSION,
                        "entries": result.get("entries") or [],
                        "counts": result.get("counts") or {},
                        "assessed_count": result.get("assessed_count"),
                        "ok_count": result.get("ok_count"),
                        "portfolio_digest": result.get("portfolio_digest"),
                    }
                    portfolio_source = "assessed_inline"
            c["resolved_portfolio"] = resolved_portfolio
            c["portfolio_source"] = portfolio_source
            portfolio_digest = None
            if resolved_portfolio is not None:
                portfolio_digest = resolved_portfolio.get("portfolio_digest") or _sha256_json(
                    {
                        "entries": [
                            {
                                "name": e.get("name"),
                                "version": e.get("version"),
                                "defect_id": e.get("defect_id"),
                                "outcome": e.get("outcome"),
                                "impact_digest": e.get("impact_digest"),
                            }
                            for e in (resolved_portfolio.get("entries") or [])
                        ],
                        "counts": resolved_portfolio.get("counts") or {},
                    }
                )
            c["portfolio_digest"] = portfolio_digest
            return {
                "stage": "portfolio",
                "ok": True,
                "verdict": "portfolio_ready" if resolved_portfolio is not None else "portfolio_none",
                "portfolio_source": portfolio_source,
                "portfolio_digest": portfolio_digest,
            }
        if name == "rank":
            inventory = list(c.get("inventory") or [])
            resolved_portfolio = c.get("resolved_portfolio")
            actions = rank_fleet_actions(inventory, resolved_portfolio)
            campaignable = [a for a in actions if a.get("campaignable")]
            c["actions"] = actions
            c["campaignable"] = campaignable
            return {
                "stage": "rank",
                "ok": True,
                "verdict": "ranked",
                "action_count": len(actions),
                "campaignable_count": len(campaignable),
                "top_action": actions[0] if actions else None,
                "action_counts": _action_counts(actions),
            }
        if name == "dispatch":
            campaignable = list(c.get("campaignable") or [])
            dispatches: list[dict[str, Any]] = []
            dispatch_digests: dict[str, str] = {}
            if campaignable:
                runner = c.get("campaign_runner") or (
                    lambda target_dir, **kwargs: ucamp.run_campaign(
                        Path(target_dir), **kwargs
                    )
                )
                limit = max(0, int(c.get("dispatch_limit") or 0))
                for action in campaignable[:limit]:
                    target_dir = action.get("target_dir")
                    if not target_dir:
                        dispatches.append({
                            "action": action.get("action"),
                            "name": action.get("name"),
                            "version": action.get("version"),
                            "defect_id": action.get("defect_id"),
                            "ok": False,
                            "verdict": "no_target_dir",
                            "detail": "action has no resolvable target_dir",
                        })
                        continue
                    camp_stages = tuple(
                        action.get("suggested_stages")
                        or ("repair", "contribution", "publication")
                    )
                    defect_ids = (
                        [action["defect_id"]] if action.get("defect_id") else None
                    )
                    try:
                        result = runner(
                            target_dir,
                            defect_ids=defect_ids,
                            stages=camp_stages,
                            publish=False,
                        )
                    except Exception as exc:  # noqa: BLE001 — dispatch isolation
                        dispatches.append({
                            "action": action.get("action"),
                            "name": action.get("name"),
                            "version": action.get("version"),
                            "defect_id": action.get("defect_id"),
                            "target_dir": target_dir,
                            "ok": False,
                            "verdict": "dispatch_error",
                            "detail": f"{type(exc).__name__}: {exc}"[:400],
                        })
                        continue
                    entry: dict[str, Any] = {
                        "action": action.get("action"),
                        "name": action.get("name"),
                        "version": action.get("version"),
                        "defect_id": action.get("defect_id"),
                        "target_dir": target_dir,
                        "stages": list(camp_stages),
                        "ok": bool(result.get("ok")),
                        "verdict": result.get("verdict"),
                        "campaign_dir": result.get("campaign_dir"),
                        "campaign_digest": result.get("campaign_digest"),
                    }
                    if result.get("campaign_dir") and result.get("campaign_digest"):
                        key = (
                            f"{action.get('name')}-{action.get('version')}-"
                            f"{action.get('defect_id') or action.get('action')}"
                        )
                        dispatch_digests[key] = str(result["campaign_digest"])
                        entry["dispatch_key"] = key
                    dispatches.append(entry)
            c["dispatches"] = dispatches
            c["dispatch_digests"] = dispatch_digests
            dispatched_ok = sum(1 for d in dispatches if d.get("ok"))
            ok = True
            verdict = "fleet_dispatched" if dispatched_ok else (
                "dispatch_failed" if dispatches else "nothing_to_dispatch"
            )
            if dispatches and dispatched_ok == 0:
                ok = False
                verdict = "dispatch_failed"
            return {
                "stage": "dispatch",
                "ok": ok,
                "verdict": verdict,
                "dispatches": dispatches,
                "dispatched_count": len(dispatches),
                "dispatched_ok": dispatched_ok,
                "dispatch_digests": dispatch_digests,
            }
        raise FleetRefused("stages_unknown", f"unknown stage {name!r}")

    def classify(state: se.PipelineState) -> tuple[bool, str]:
        if state.aborted:
            return False, state.terminal_verdict
        if not state.pipeline_ok:
            return False, state.terminal_verdict
        c = state.context
        dispatches = list(c.get("dispatches") or [])
        campaignable = list(c.get("campaignable") or [])
        actions = list(c.get("actions") or [])
        dispatched_ok = sum(1 for d in dispatches if d.get("ok"))
        if "dispatch" in state.stage_results:
            if campaignable and dispatched_ok == 0 and dispatches:
                return False, "dispatch_failed"
            if dispatched_ok:
                return True, "fleet_dispatched"
        if campaignable:
            return True, "fleet_ranked"
        if actions:
            return True, "fleet_monitor_only"
        return True, "fleet_idle"

    def seal(state: se.PipelineState) -> dict[str, Any]:
        c = state.context
        if state.aborted:
            ok = False
            verdict = state.terminal_verdict
        else:
            ok, verdict = classify(state)
            state.pipeline_ok = ok
            state.terminal_verdict = verdict
        return _seal_fleet_plan(
            inventory=list(c.get("inventory") or []),
            resolved_portfolio=c.get("resolved_portfolio"),
            portfolio_source=str(c.get("portfolio_source") or "none"),
            portfolio_digest=c.get("portfolio_digest"),
            actions=list(c.get("actions") or []),
            campaignable=list(c.get("campaignable") or []),
            dispatches=list(c.get("dispatches") or []),
            dispatch_digests=dict(c.get("dispatch_digests") or {}),
            ok=ok,
            verdict=verdict,
            out_root=c.get("out_root"),
            stages=state.stages,
            stage_results=state.stage_results,
        )

    def wrap_refuse(exc: BaseException) -> BaseException:
        if isinstance(exc, se.StageRefused):
            return FleetRefused(exc.verdict, exc.detail)
        return exc

    return se.run_stage_pipeline(
        "fleet",
        stages=stage_list,
        run_stage=run_stage,
        classify_verdict=classify,
        seal=seal,
        initial_context=ctx,
        initial_verdict="fleet_ranked",
        wrap_refuse=wrap_refuse,
    )


def _seal_fleet_plan(
    *,
    inventory: Sequence[Mapping[str, Any]],
    resolved_portfolio: Mapping[str, Any] | None,
    portfolio_source: str,
    portfolio_digest: str | None,
    actions: Sequence[Mapping[str, Any]],
    campaignable: Sequence[Mapping[str, Any]],
    dispatches: Sequence[Mapping[str, Any]],
    dispatch_digests: Mapping[str, str],
    ok: bool,
    verdict: str,
    out_root: Path | None,
    stages: Sequence[str],
    stage_results: Mapping[str, Any],
) -> dict[str, Any]:
    """Write the historical fleet plan.json seal (digest-compatible)."""
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    plan_dir = root / stamp
    plan_dir.mkdir(parents=True, exist_ok=True)

    inventory_digest = _sha256_json(_inventory_digest_payload(inventory))
    actions_digest = _sha256_json(_actions_digest_payload(actions))
    dispatched_ok = sum(1 for d in dispatches if d.get("ok"))

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "inventory": list(inventory),
        "inventory_digest": inventory_digest,
        "inventory_count": len(inventory),
        "portfolio_source": portfolio_source,
        "portfolio_digest": portfolio_digest,
        "portfolio_counts": (
            (resolved_portfolio or {}).get("counts") if resolved_portfolio else {}
        ),
        "actions": list(actions),
        "actions_digest": actions_digest,
        "action_count": len(actions),
        "action_counts": _action_counts(actions),
        "campaignable_count": len(campaignable),
        "top_action": actions[0] if actions else None,
        "dispatches": list(dispatches),
        "dispatched_count": len(dispatches),
        "dispatched_ok": dispatched_ok,
        "dispatch_digests": dict(dispatch_digests),
        "stages": list(stages),
        "stage_results": dict(stage_results),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "stage_engine": True,
        "pipeline_dialect": STAGE_ENGINE_DIALECT,
    }
    plan["fleet_digest"] = _sha256_json(_plan_digest_payload(plan))
    atomic_write_json(plan_dir / "plan.json", plan)

    atomic_write_json(
        plan_dir / "summary.json",
        {
            "verdict": plan["verdict"],
            "ok": plan["ok"],
            "inventory_count": plan["inventory_count"],
            "action_count": plan["action_count"],
            "action_counts": plan["action_counts"],
            "campaignable_count": plan["campaignable_count"],
            "top_action": plan["top_action"],
            "dispatched_ok": plan["dispatched_ok"],
            "fleet_digest": plan["fleet_digest"],
            "stage_engine": True,
            "pipeline_dialect": STAGE_ENGINE_DIALECT,
        },
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "plan_dir": str(plan_dir),
        "fleet_digest": plan["fleet_digest"],
        "inventory_count": plan["inventory_count"],
        "action_count": plan["action_count"],
        "action_counts": plan["action_counts"],
        "campaignable_count": plan["campaignable_count"],
        "top_action": plan["top_action"],
        "dispatches": list(dispatches),
        "dispatched_count": plan["dispatched_count"],
        "dispatched_ok": plan["dispatched_ok"],
        "portfolio_source": portfolio_source,
        "portfolio_digest": portfolio_digest,
        "stages": list(stages),
        "stage_results": dict(stage_results),
        "used_skill_route_discovery": plan["used_skill_route_discovery"],
        "stage_engine": True,
        "pipeline_dialect": STAGE_ENGINE_DIALECT,
    }


def verify_fleet_plan(plan_dir: Path) -> dict[str, Any]:
    """Re-check a sealed fleet plan; detect inventory/action/dispatch tampering."""
    plan_dir = Path(plan_dir)
    path = durable_read_path(plan_dir / "plan.json")
    if not path.is_file():
        return {"ok": False, "error": "missing plan.json", "mismatched": ["missing"]}
    plan = json.loads(path.read_text(encoding="utf-8"))
    mismatched: list[str] = []
    problems: list[str] = []

    expected_inv = _sha256_json(_inventory_digest_payload(plan.get("inventory") or []))
    if plan.get("inventory_digest") != expected_inv:
        mismatched.append("inventory_digest")
        problems.append("inventory digest mismatch")

    expected_act = _sha256_json(_actions_digest_payload(plan.get("actions") or []))
    if plan.get("actions_digest") != expected_act:
        mismatched.append("actions_digest")
        problems.append("actions digest mismatch")

    expected_fleet = _sha256_json(_plan_digest_payload(plan))
    if plan.get("fleet_digest") != expected_fleet:
        mismatched.append("fleet_digest")
        problems.append("fleet chain digest mismatch")

    # Rank order must be priority-sorted.
    actions = list(plan.get("actions") or [])
    for i in range(1, len(actions)):
        prev_p = int(actions[i - 1].get("priority") or 999)
        cur_p = int(actions[i].get("priority") or 999)
        if cur_p < prev_p:
            problems.append(f"action rank order violated at index {i}")
            mismatched.append("rank_order")
            break

    return {
        "ok": not mismatched and not problems,
        "mismatched": mismatched,
        "problems": problems,
        "fleet_digest": plan.get("fleet_digest"),
        "verdict": plan.get("verdict"),
        "action_count": plan.get("action_count"),
        "used_skill_route_discovery": plan.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_target(
    scratch: Path,
    *,
    name: str,
    version: str,
    defects: Sequence[Mapping[str, Any]],
) -> Path:
    target = scratch / f"{name}-{version}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
                "version": version,
                "upstream_repo": f"https://github.com/proof/{name}",
                "sdist": f"{name}-{version}.tar.gz",
                "sdist_sha256": "0" * 64,
                "defects": list(defects),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Touch patch/repro files so inventory "patch-bound" is honest if needed.
    for d in defects:
        if d.get("patch"):
            p = target / str(d["patch"])
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.is_file():
                p.write_text("# proof patch\n", encoding="utf-8")
        if d.get("repro"):
            r = target / str(d["repro"])
            r.parent.mkdir(parents=True, exist_ok=True)
            if not r.is_file():
                r.write_text("# proof repro\n", encoding="utf-8")
    return target


def _proof_portfolio(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for e in entries:
        o = str(e.get("outcome") or "unknown")
        counts[o] = counts.get(o, 0) + 1
    portfolio: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "assessed_count": len(entries),
        "ok_count": len(entries),
        "failure_count": 0,
        "counts": counts,
        "entries": list(entries),
        "failures": [],
        "used_skill_route_discovery": False,
    }
    portfolio["portfolio_digest"] = _sha256_json(
        {
            "entries": [
                {
                    "name": e.get("name"),
                    "version": e.get("version"),
                    "defect_id": e.get("defect_id"),
                    "outcome": e.get("outcome"),
                    "impact_digest": e.get("impact_digest"),
                }
                for e in entries
            ],
            "counts": counts,
        }
    )
    return portfolio


def builtin_upstream_fleet_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the fleet plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="fleet-proof-"))
    try:
        stew = scratch / "stewardship"
        stew.mkdir()

        # Target A: patch-bound defect with closed-unmerged impact → rework tops rank.
        _proof_target(
            stew,
            name="alpha",
            version="1.0.0",
            defects=[{
                "id": "alpha-dos",
                "title": "alpha dos",
                "kind": "complexity",
                "patch": "patches/alpha-dos.patch",
                "repro": "repros/alpha_dos.py",
            }],
        )
        # Target B: empty frontier → discover_empty.
        _proof_target(stew, name="beta", version="2.0.0", defects=[])
        # Target C: pending-patch admission → bind_pending_patch.
        _proof_target(
            stew,
            name="gamma",
            version="3.0.0",
            defects=[{
                "id": "gamma-pending",
                "title": "gamma pending",
                "kind": "complexity",
                "pending_patch": True,
                "repro": "repros/gamma_pending.py",
            }],
        )
        # Target D: already released → done_released, not campaignable.
        _proof_target(
            stew,
            name="delta",
            version="4.0.0",
            defects=[{
                "id": "delta-fix",
                "title": "delta fixed",
                "kind": "correctness",
                "patch": "patches/delta-fix.patch",
                "repro": "repros/delta_fix.py",
            }],
        )
        # Target E: open PR → follow_open.
        _proof_target(
            stew,
            name="epsilon",
            version="5.0.0",
            defects=[{
                "id": "epsilon-open",
                "title": "epsilon open",
                "kind": "complexity",
                "patch": "patches/epsilon-open.patch",
                "repro": "repros/epsilon_open.py",
            }],
        )
        # Target F: patch-bound with no portfolio entry → campaign_patch_bound.
        _proof_target(
            stew,
            name="zeta",
            version="6.0.0",
            defects=[{
                "id": "zeta-ready",
                "title": "zeta ready",
                "kind": "complexity",
                "patch": "patches/zeta-ready.patch",
                "repro": "repros/zeta_ready.py",
            }],
        )

        portfolio = _proof_portfolio([
            {
                "name": "alpha",
                "version": "1.0.0",
                "defect_id": "alpha-dos",
                "outcome": "impact_closed_unmerged",
                "impact_digest": "a" * 64,
                "pr_number": 11,
                "pr_url": "https://github.com/proof/alpha/pull/11",
                "ok": True,
            },
            {
                "name": "delta",
                "version": "4.0.0",
                "defect_id": "delta-fix",
                "outcome": "impact_released",
                "impact_digest": "b" * 64,
                "pr_number": 22,
                "pr_url": "https://github.com/proof/delta/pull/22",
                "ok": True,
            },
            {
                "name": "epsilon",
                "version": "5.0.0",
                "defect_id": "epsilon-open",
                "outcome": "impact_open",
                "impact_digest": "c" * 64,
                "pr_number": 33,
                "pr_url": "https://github.com/proof/epsilon/pull/33",
                "ok": True,
            },
        ])

        # 1) Rank without dispatch: rework must outrank discover/campaign/follow/done.
        ranked = plan_fleet(
            stewardship_root=stew,
            portfolio=portfolio,
            dispatch=False,
            out_root=scratch / "plans-ranked",
        )
        top = ranked.get("top_action") or {}
        rank_ok = (
            ranked["ok"]
            and ranked["verdict"] == "fleet_ranked"
            and ranked["inventory_count"] == 6
            and ranked["campaignable_count"] >= 3
            and top.get("action") == "rework_closed_unmerged"
            and top.get("name") == "alpha"
            and top.get("defect_id") == "alpha-dos"
        )
        counts = ranked.get("action_counts") or {}
        counts_ok = (
            counts.get("rework_closed_unmerged") == 1
            and counts.get("done_released") == 1
            and counts.get("follow_open") == 1
            and counts.get("discover_empty") == 1
            and counts.get("bind_pending_patch") == 1
            and counts.get("campaign_patch_bound") == 1  # zeta only
        )
        plan_dir = Path(ranked["plan_dir"])
        verified = verify_fleet_plan(plan_dir)
        verify_ok = bool(verified.get("ok"))

        # 2) Tamper detection.
        plan_path = plan_dir / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["fleet_digest"] = "0" * 64
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        tampered = verify_fleet_plan(plan_dir)
        tamper_detected = (
            not tampered["ok"] and "fleet_digest" in (tampered.get("mismatched") or [])
        )

        # 3) Dispatch top campaignable action through injected campaign seam.
        dispatch_calls: list[dict[str, Any]] = []

        def campaign_inject(target_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
            dispatch_calls.append({
                "target_dir": str(target_dir),
                "defect_ids": kwargs.get("defect_ids"),
                "stages": kwargs.get("stages"),
            })
            digest = _sha256_json({
                "target": str(target_dir),
                "defect_ids": kwargs.get("defect_ids"),
                "stages": list(kwargs.get("stages") or []),
            })
            camp_dir = scratch / "dispatched-campaigns" / Path(str(target_dir)).name
            camp_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                camp_dir / "receipt.json",
                {
                    "ok": True,
                    "verdict": "dispatched_proof",
                    "campaign_digest": digest,
                },
            )
            return {
                "ok": True,
                "verdict": "dispatched_proof",
                "campaign_dir": str(camp_dir),
                "campaign_digest": digest,
            }

        dispatched = plan_fleet(
            stewardship_root=stew,
            portfolio=portfolio,
            dispatch=True,
            dispatch_limit=1,
            campaign_runner=campaign_inject,
            out_root=scratch / "plans-dispatch",
        )
        dispatch_ok = (
            dispatched["ok"]
            and dispatched["verdict"] == "fleet_dispatched"
            and dispatched["dispatched_ok"] == 1
            and len(dispatch_calls) == 1
            and "alpha-1.0.0" in dispatch_calls[0]["target_dir"].replace("\\", "/")
            and dispatch_calls[0]["defect_ids"] == ["alpha-dos"]
        )
        dispatch_verified = verify_fleet_plan(Path(dispatched["plan_dir"]))
        dispatch_seal_ok = bool(dispatch_verified.get("ok"))
        # Fleet plan must chain the campaign digest.
        disp_plan = json.loads(
            (Path(dispatched["plan_dir"]) / "plan.json").read_text(encoding="utf-8")
        )
        dispatch_chained = bool(disp_plan.get("dispatch_digests"))

        # 4) Empty stewardship + no portfolio refuses.
        empty_root = scratch / "empty-stew"
        empty_root.mkdir()
        empty_refused = False
        try:
            plan_fleet(stewardship_root=empty_root, dispatch=False, out_root=scratch / "empty")
        except FleetRefused as exc:
            empty_refused = exc.verdict == "fleet_empty"

        # 5) Portfolio-only monitor: all terminal → fleet_monitor_only / idle ranks.
        monitor_stew = scratch / "monitor-stew"
        monitor_stew.mkdir()
        _proof_target(
            monitor_stew,
            name="omega",
            version="9.0.0",
            defects=[{
                "id": "omega-merged",
                "title": "omega",
                "kind": "correctness",
                "patch": "patches/omega.patch",
                "repro": "repros/omega.py",
            }],
        )
        monitor_portfolio = _proof_portfolio([{
            "name": "omega",
            "version": "9.0.0",
            "defect_id": "omega-merged",
            "outcome": "impact_merged",
            "impact_digest": "d" * 64,
            "ok": True,
        }])
        monitor = plan_fleet(
            stewardship_root=monitor_stew,
            portfolio=monitor_portfolio,
            dispatch=False,
            out_root=scratch / "plans-monitor",
        )
        monitor_ok = (
            monitor["ok"]
            and monitor["verdict"] == "fleet_monitor_only"
            and monitor["campaignable_count"] == 0
            and (monitor.get("top_action") or {}).get("action") == "done_merged"
        )

        # 6) Injected portfolio_runner path (assess_portfolio=True).
        assessed_calls = {"n": 0}

        def portfolio_inject(**_kwargs: Any) -> dict[str, Any]:
            assessed_calls["n"] += 1
            pdir = scratch / "injected-portfolio"
            pdir.mkdir(parents=True, exist_ok=True)
            # Write a seal-compatible portfolio for source=assessed.
            atomic_write_json(pdir / "portfolio.json", portfolio)
            return {
                "ok": True,
                "portfolio_dir": str(pdir),
                "portfolio_digest": portfolio["portfolio_digest"],
                "entries": portfolio["entries"],
                "counts": portfolio["counts"],
                "assessed_count": portfolio["assessed_count"],
                "ok_count": portfolio["ok_count"],
            }

        assessed = plan_fleet(
            stewardship_root=stew,
            assess_portfolio=True,
            portfolio_runner=portfolio_inject,
            dispatch=False,
            out_root=scratch / "plans-assessed",
        )
        assessed_ok = (
            assessed["ok"]
            and assessed_calls["n"] == 1
            and assessed.get("portfolio_source") == "assessed"
            and (assessed.get("top_action") or {}).get("action") == "rework_closed_unmerged"
        )

        # 7) Priority: diverged outranks discover_empty and campaign_patch_bound.
        priority_actions = rank_fleet_actions(
            inventory_targets(stew),
            _proof_portfolio([
                {
                    "name": "alpha",
                    "version": "1.0.0",
                    "defect_id": "alpha-dos",
                    "outcome": "impact_open_diverged",
                    "impact_digest": "e" * 64,
                    "ok": True,
                },
            ]),
        )
        priority_ok = (
            priority_actions
            and priority_actions[0]["action"] == "rework_diverged"
            and priority_actions[0]["priority"]
            < ACTION_PRIORITY["campaign_patch_bound"]
            and priority_actions[0]["priority"]
            < ACTION_PRIORITY["discover_empty"]
        )

        stage_engine_owned = (
            STAGE_ENGINE is True
            and STAGE_ENGINE_DIALECT == "fleet"
            and ranked.get("stage_engine") is True
            and ranked.get("pipeline_dialect") == "fleet"
            and dispatched.get("stage_engine") is True
            and dispatched.get("pipeline_dialect") == "fleet"
        )

        ok = all([
            rank_ok,
            counts_ok,
            verify_ok,
            tamper_detected,
            dispatch_ok,
            dispatch_seal_ok,
            dispatch_chained,
            empty_refused,
            monitor_ok,
            assessed_ok,
            priority_ok,
            stage_engine_owned,
        ])
        return {
            "ok": ok,
            "inventory_ranked": rank_ok and counts_ok,
            "rework_outranks": rank_ok and priority_ok,
            "plan_verified": verify_ok,
            "tamper_detected": tamper_detected,
            "dispatch_chained": dispatch_ok and dispatch_seal_ok and dispatch_chained,
            "empty_refused": empty_refused,
            "monitor_only": monitor_ok,
            "portfolio_assessed_path": assessed_ok,
            "stage_engine_owned": stage_engine_owned,
            "stage_engine": True,
            "pipeline_dialect": STAGE_ENGINE_DIALECT,
            "fleet_digest": ranked.get("fleet_digest"),
            "dispatch_fleet_digest": dispatched.get("fleet_digest"),
            "action_counts": counts,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="List stewardship target readiness")
    inv.add_argument(
        "--stewardship-root",
        type=Path,
        default=None,
        help="override stewardship root (default: ./stewardship)",
    )

    plan_p = sub.add_parser("plan", help="Rank fleet actions and seal a plan")
    plan_p.add_argument("--stewardship-root", type=Path, default=None)
    plan_p.add_argument("--portfolio-dir", type=Path, default=None)
    plan_p.add_argument(
        "--assess-portfolio",
        action="store_true",
        help="assess live impact portfolio before ranking",
    )
    plan_p.add_argument(
        "--dispatch",
        action="store_true",
        help="dispatch top campaignable action(s) through the campaign plane",
    )
    plan_p.add_argument("--dispatch-limit", type=int, default=1)
    plan_p.add_argument("--out-root", type=Path, default=None)

    ver = sub.add_parser("verify", help="Verify a sealed fleet plan")
    ver.add_argument("plan_dir", type=Path)

    proof = sub.add_parser("proof", help="Run hermetic builtin proof")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "inventory":
        items = inventory_targets(args.stewardship_root)
        print(json.dumps({"count": len(items), "targets": items}, indent=2))
        return 0

    if args.cmd == "plan":
        try:
            result = plan_fleet(
                stewardship_root=args.stewardship_root,
                portfolio_dir=args.portfolio_dir,
                assess_portfolio=args.assess_portfolio,
                dispatch=args.dispatch,
                dispatch_limit=args.dispatch_limit,
                out_root=args.out_root,
            )
        except FleetRefused as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 2
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify":
        result = verify_fleet_plan(args.plan_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "proof":
        result = builtin_upstream_fleet_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
