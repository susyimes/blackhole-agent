"""Upstream epoch plane: multi-wave closed-loop fleet stewardship.

The fleet plane (``upstream_fleet``) inventories targets, ranks next actions
from an impact portfolio, and optionally dispatches *once*. An epoch closes
the multi-wave loop the fleet deliberately leaves open:

1. **wave** — call the fleet plane (injected ``fleet_runner`` seam; default
   ``plan_fleet``) with the current portfolio world-model, optionally
   dispatching up to ``per_wave_dispatch_limit`` campaignable actions;
2. **feedback** — map wave dispatches into portfolio entry updates via an
   injected ``feedback_runner`` (default: successful campaignable dispatches
   become ``impact_open`` so the next wave will not re-campaign them; terminal
   outcomes can be injected for hermetic proofs);
3. **re-rank** — the next wave re-inventories + re-ranks against the updated
   portfolio so urgency order can change mid-epoch (rework → follow, campaign
   → done, empty → discover still pending, …);
4. **stop** when any of:

   - ``max_waves`` reached
   - ``dispatch_budget`` exhausted (total successful+attempted dispatches)
   - no campaignable actions remain (``epoch_idle`` / monitor-only)
   - consecutive no-progress waves (``no_progress_limit``): zero successful
     dispatches while campaignable work existed, or the campaignable set
     digest is unchanged after a dispatching wave
   - explicit ``stop_when`` predicate returns a reason string

5. **seal** — write an epoch receipt under ``artifacts/upstream-epoch/`` with
   sha256 digests of every wave fleet plan, the evolving portfolio, stop
   reason, and an epoch chain digest; ``verify_epoch_receipt`` re-checks the
   chain and detects tampering.

No skill-route discovery is used. The plane is closed-loop direction over the
fleet plane, not a new verifier of individual repairs.
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

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_loop_engine as le
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

# Owned by the multi-round durable loop engine (not a copy-paste tower).
LOOP_ENGINE = True
LOOP_DIALECT = "epoch"

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-epoch"

# Default: after a successful dispatch, treat the defect as an open PR so the
# next wave monitors rather than re-campaigns (unless feedback injects better).
DEFAULT_POST_DISPATCH_OUTCOME = "impact_open"


class EpochRefused(Exception):
    """A verdict-bearing refusal: the epoch must not continue."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


# ---------------------------------------------------------------------------
# digests / io


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(canonical.encode("utf-8"))


def _portfolio_entries(portfolio: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not portfolio:
        return []
    return [dict(e) for e in (portfolio.get("entries") or []) if isinstance(e, Mapping)]


def _recompute_portfolio_digest(portfolio: Mapping[str, Any]) -> str:
    entries = _portfolio_entries(portfolio)
    counts: dict[str, int] = {}
    for e in entries:
        o = str(e.get("outcome") or "unknown")
        counts[o] = counts.get(o, 0) + 1
    return _sha256_json(
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


def _campaignable_set_digest(actions: Sequence[Mapping[str, Any]]) -> str:
    keys = sorted(
        {
            (
                str(a.get("action") or ""),
                str(a.get("name") or ""),
                str(a.get("version") or ""),
                str(a.get("defect_id") or ""),
            )
            for a in actions
            if a.get("campaignable")
        }
    )
    return _sha256_json(keys)


# ---------------------------------------------------------------------------
# portfolio feedback


def default_dispatch_feedback(
    portfolio: Mapping[str, Any] | None,
    dispatches: Sequence[Mapping[str, Any]],
    *,
    post_dispatch_outcome: str = DEFAULT_POST_DISPATCH_OUTCOME,
) -> dict[str, Any]:
    """Merge successful dispatches into the portfolio as follow/terminal outcomes.

    Successful campaignable dispatches receive ``post_dispatch_outcome``
    (default ``impact_open``) so the next wave will not re-dispatch them as
    campaign work. Failed dispatches leave prior portfolio state untouched.
    Returns a full portfolio dict with recomputed digest and counts.
    """
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in _portfolio_entries(portfolio):
        key = (
            str(e.get("name") or ""),
            str(e.get("version") or ""),
            str(e.get("defect_id") or ""),
        )
        by_key[key] = dict(e)

    applied: list[dict[str, Any]] = []
    for d in dispatches:
        if not d.get("ok"):
            continue
        name = str(d.get("name") or "")
        version = str(d.get("version") or "")
        defect_id = str(d.get("defect_id") or "") or None
        if not name or defect_id is None:
            # discover_empty may lack defect_id — still record a synthetic follow.
            if d.get("action") == "discover_empty" and name:
                # Discovery does not create portfolio PR outcomes; skip portfolio.
                applied.append({
                    "action": d.get("action"),
                    "name": name,
                    "version": version,
                    "skipped": "discover_empty_no_portfolio_row",
                })
                continue
            continue
        key = (name, version, defect_id)
        prior = by_key.get(key) or {}
        impact_digest = _sha256_json(
            {
                "source": "epoch_dispatch_feedback",
                "name": name,
                "version": version,
                "defect_id": defect_id,
                "campaign_digest": d.get("campaign_digest"),
                "outcome": post_dispatch_outcome,
            }
        )
        entry = {
            **prior,
            "name": name,
            "version": version,
            "defect_id": defect_id,
            "outcome": post_dispatch_outcome,
            "impact_digest": impact_digest,
            "ok": True,
            "source": "epoch_dispatch_feedback",
            "campaign_digest": d.get("campaign_digest"),
            "campaign_dir": d.get("campaign_dir"),
            "action": d.get("action"),
        }
        by_key[key] = entry
        applied.append({
            "name": name,
            "version": version,
            "defect_id": defect_id,
            "outcome": post_dispatch_outcome,
            "prior_outcome": prior.get("outcome"),
        })

    entries = list(by_key.values())
    counts: dict[str, int] = {}
    for e in entries:
        o = str(e.get("outcome") or "unknown")
        counts[o] = counts.get(o, 0) + 1
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "assessed_count": len(entries),
        "ok_count": sum(1 for e in entries if e.get("ok")),
        "failure_count": 0,
        "counts": counts,
        "entries": entries,
        "failures": [],
        "feedback_applied": applied,
        "used_skill_route_discovery": False,
    }
    result["portfolio_digest"] = _recompute_portfolio_digest(result)
    return result


# ---------------------------------------------------------------------------
# epoch seal / verify


def _epoch_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "wave_count": receipt.get("wave_count"),
        "wave_digests": receipt.get("wave_digests") or [],
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "stop_reason": receipt.get("stop_reason"),
        "ok": receipt.get("ok"),
        "verdict": receipt.get("verdict"),
    }


def _wave_record(
    *,
    wave_index: int,
    fleet_result: Mapping[str, Any],
    portfolio_before_digest: str | None,
    portfolio_after_digest: str | None,
    feedback_applied: Sequence[Mapping[str, Any]],
    campaignable_digest: str,
) -> dict[str, Any]:
    return {
        "wave": wave_index,
        "ok": bool(fleet_result.get("ok")),
        "verdict": fleet_result.get("verdict"),
        "plan_dir": fleet_result.get("plan_dir"),
        "fleet_digest": fleet_result.get("fleet_digest"),
        "inventory_count": fleet_result.get("inventory_count"),
        "action_count": fleet_result.get("action_count"),
        "action_counts": fleet_result.get("action_counts") or {},
        "campaignable_count": fleet_result.get("campaignable_count"),
        "campaignable_digest": campaignable_digest,
        "top_action": fleet_result.get("top_action"),
        "dispatched_count": fleet_result.get("dispatched_count") or 0,
        "dispatched_ok": fleet_result.get("dispatched_ok") or 0,
        "dispatches": list(fleet_result.get("dispatches") or []),
        "dispatch_digests": dict(fleet_result.get("dispatch_digests") or {}),
        "portfolio_before_digest": portfolio_before_digest,
        "portfolio_after_digest": portfolio_after_digest,
        "feedback_applied": list(feedback_applied),
    }


def verify_epoch_receipt(epoch_dir: Path) -> dict[str, Any]:
    """Re-check a sealed epoch receipt; detect wave/portfolio chain tampering."""
    epoch_dir = Path(epoch_dir)
    path = durable_read_path(epoch_dir / "epoch.json")
    if not path.is_file():
        return {"ok": False, "error": "missing epoch.json", "mismatched": ["missing"]}
    receipt = json.loads(path.read_text(encoding="utf-8"))
    mismatched: list[str] = []
    problems: list[str] = []

    waves = list(receipt.get("waves") or [])
    expected_wave_digests = [
        w.get("fleet_digest") for w in waves if w.get("fleet_digest")
    ]
    if list(receipt.get("wave_digests") or []) != expected_wave_digests:
        mismatched.append("wave_digests")
        problems.append("wave_digests does not match waves[].fleet_digest")

    if receipt.get("wave_count") != len(waves):
        mismatched.append("wave_count")
        problems.append("wave_count mismatch")

    expected_epoch = _sha256_json(_epoch_digest_payload(receipt))
    if receipt.get("epoch_digest") != expected_epoch:
        mismatched.append("epoch_digest")
        problems.append("epoch chain digest mismatch")

    # Monotonic wave indices (wave 0 is valid; do not treat 0 as missing).
    for i, w in enumerate(waves):
        if w.get("wave") != i:
            problems.append(f"wave index disorder at {i}")
            mismatched.append("wave_order")
            break

    return {
        "ok": not mismatched and not problems,
        "mismatched": mismatched,
        "problems": problems,
        "epoch_digest": receipt.get("epoch_digest"),
        "verdict": receipt.get("verdict"),
        "wave_count": receipt.get("wave_count"),
        "used_skill_route_discovery": receipt.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# run epoch


def run_epoch(
    *,
    stewardship_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    max_waves: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    no_progress_limit: int = 1,
    dispatch: bool = True,
    assess_portfolio: bool = False,
    fleet_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    portfolio_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    post_dispatch_outcome: str = DEFAULT_POST_DISPATCH_OUTCOME,
    out_root: Path | None = None,
    fleet_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-wave closed-loop fleet epoch and seal the receipt.

    Control flow is owned by :mod:`blackhole_agent.upstream_loop_engine`;
    this module supplies epoch-dialect hooks (fleet feedback, campaignable
    progress, receipt schema) only.

    Parameters
    ----------
    max_waves:
        Hard cap on fleet plan waves (including non-dispatch ranking waves).
    per_wave_dispatch_limit:
        Forwarded to the fleet plane as ``dispatch_limit`` each wave.
    dispatch_budget:
        Total dispatch *attempts* across the epoch; ``None`` means unlimited
        (still bounded by ``max_waves * per_wave_dispatch_limit``).
    no_progress_limit:
        Stop after this many consecutive waves that fail to advance the
        campaignable set (no successful dispatch while work remained, or
        campaignable digest unchanged after a dispatching wave).
    dispatch:
        When False, waves only rank (still multi-wave if portfolio feedback is
        externally injected via ``feedback_runner``; default feedback is a
        no-op without dispatches).
    fleet_runner / feedback_runner / campaign_runner:
        Injected seams for hermetic proofs.
    """
    if max_waves < 1:
        raise EpochRefused("epoch_invalid", "max_waves must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise EpochRefused("epoch_invalid", "per_wave_dispatch_limit must be >= 0")

    dialect = le.get_loop_dialect("epoch")
    runner = fleet_runner or uf.plan_fleet
    feedback = feedback_runner or (
        lambda port, disps, **kw: default_dispatch_feedback(
            port,
            disps,
            post_dispatch_outcome=kw.get(
                "post_dispatch_outcome", post_dispatch_outcome
            ),
        )
    )

    def extract_dispatched(result: dict[str, Any]) -> tuple[int, int]:
        return (
            int(result.get("dispatched_count") or 0),
            int(result.get("dispatched_ok") or 0),
        )

    def build_child_kwargs(state: le.LoopState, round_index: int) -> dict[str, Any]:
        remaining = None
        if state.dispatch_budget is not None:
            remaining = max(0, int(state.dispatch_budget) - state.total_dispatched)
        wave_limit = per_wave_dispatch_limit
        if remaining is not None:
            wave_limit = min(wave_limit, remaining)
        kwargs: dict[str, Any] = {
            "stewardship_root": stewardship_root,
            "portfolio": state.portfolio,
            "dispatch": bool(dispatch) and wave_limit > 0,
            "dispatch_limit": wave_limit,
            "assess_portfolio": (
                assess_portfolio
                and round_index == 0
                and state.portfolio is None
            ),
            "out_root": state.child_root / f"wave-{round_index:02d}",
        }
        if campaign_runner is not None:
            kwargs["campaign_runner"] = campaign_runner
        if portfolio_runner is not None:
            kwargs["portfolio_runner"] = portfolio_runner
        return kwargs

    def on_child_result(
        state: le.LoopState, round_index: int, fleet_result: dict[str, Any]
    ) -> dict[str, Any]:
        portfolio_before = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        plan_actions: list[Any] = []
        plan_dir = fleet_result.get("plan_dir")
        if plan_dir and (Path(plan_dir) / "plan.json").is_file():
            plan = json.loads(
                (Path(plan_dir) / "plan.json").read_text(encoding="utf-8")
            )
            plan_actions = list(plan.get("actions") or [])
        camp_digest = _campaignable_set_digest(plan_actions)

        dispatches = list(fleet_result.get("dispatches") or [])
        campaignable_count = int(fleet_result.get("campaignable_count") or 0)
        state.extras["last_campaignable_count"] = campaignable_count
        state.extras["last_campaignable_digest"] = camp_digest

        feedback_applied: list[dict[str, Any]] = []
        if dispatches:
            updated = feedback(
                state.portfolio,
                dispatches,
                post_dispatch_outcome=post_dispatch_outcome,
            )
            if isinstance(updated, Mapping):
                state.portfolio = dict(updated)
                feedback_applied = list(
                    state.portfolio.pop("feedback_applied", []) or []
                )
                if "portfolio_digest" not in state.portfolio:
                    state.portfolio["portfolio_digest"] = _recompute_portfolio_digest(
                        state.portfolio
                    )

        portfolio_after = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        if fleet_result.get("fleet_digest"):
            state.child_digests.append(str(fleet_result["fleet_digest"]))

        # Track no-progress dialect state (not simple idle).
        prev = state.extras.get("prev_campaignable_digest")
        portfolio_changed = portfolio_before != portfolio_after
        set_changed = prev is not None and camp_digest != prev
        advanced = bool(portfolio_changed or set_changed)
        if advanced:
            state.extras["no_progress_streak"] = 0
        else:
            state.extras["no_progress_streak"] = int(
                state.extras.get("no_progress_streak") or 0
            ) + 1
        state.extras["prev_campaignable_digest"] = camp_digest

        return _wave_record(
            wave_index=round_index,
            fleet_result=fleet_result,
            portfolio_before_digest=portfolio_before,
            portfolio_after_digest=portfolio_after,
            feedback_applied=feedback_applied,
            campaignable_digest=camp_digest,
        )

    def post_round_stop(
        state: le.LoopState, round_index: int, fleet_result: dict[str, Any]
    ) -> str | None:
        if stop_when is not None:
            reason = stop_when(
                {
                    "wave_index": round_index,
                    "fleet_result": fleet_result,
                    "portfolio": state.portfolio,
                    "waves": state.records,
                    "total_dispatched": state.total_dispatched,
                    "total_dispatched_ok": state.total_dispatched_ok,
                }
            )
            if reason:
                return str(reason)
        campaignable_count = int(state.extras.get("last_campaignable_count") or 0)
        if campaignable_count == 0:
            return "epoch_idle"
        if not dispatch:
            return dialect.rank_only_stop_reason
        streak = int(state.extras.get("no_progress_streak") or 0)
        if streak >= no_progress_limit:
            return "no_progress"
        return None

    def is_idle(
        state: le.LoopState, round_index: int, fleet_result: dict[str, Any]
    ) -> bool:
        # Epoch uses campaignable idle / no_progress via post_round_stop, not
        # the engine's generic dispatch-zero idle streak.
        return False

    def classify(state: le.LoopState) -> tuple[bool, str]:
        if not state.records:
            return False, "epoch_empty"
        if state.total_dispatched_ok > 0:
            return True, "epoch_progressed"
        if any(int(w.get("campaignable_count") or 0) == 0 for w in state.records):
            if state.stop_reason == "epoch_idle" and state.total_dispatched == 0:
                return True, "epoch_idle"
            if state.stop_reason == dialect.rank_only_stop_reason:
                return True, "epoch_ranked"
            return True, "epoch_no_progress"
        if state.stop_reason == dialect.rank_only_stop_reason:
            return True, "epoch_ranked"
        if state.stop_reason == "no_progress":
            return True, "epoch_no_progress"
        return True, "epoch_completed"

    def seal(state: le.LoopState) -> dict[str, Any]:
        portfolio_end_digest = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        receipt: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now_iso(),
            "ok": state.extras.get("ok"),
            "verdict": state.extras.get("verdict"),
            "stop_reason": state.stop_reason,
            "max_waves": max_waves,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": dispatch_budget,
            "dispatch_enabled": bool(dispatch),
            "portfolio_source": state.portfolio_source,
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_final": state.portfolio,
            "wave_count": len(state.records),
            "waves": state.records,
            "wave_digests": list(state.child_digests),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }
        receipt["epoch_digest"] = _sha256_json(_epoch_digest_payload(receipt))
        atomic_write_json(state.loop_dir / "epoch.json", receipt)
        atomic_write_json(
            state.loop_dir / "summary.json",
            {
                "verdict": receipt["verdict"],
                "ok": receipt["ok"],
                "stop_reason": receipt["stop_reason"],
                "wave_count": receipt["wave_count"],
                "total_dispatched": receipt["total_dispatched"],
                "total_dispatched_ok": receipt["total_dispatched_ok"],
                "portfolio_start_digest": receipt["portfolio_start_digest"],
                "portfolio_end_digest": receipt["portfolio_end_digest"],
                "epoch_digest": receipt["epoch_digest"],
            },
        )
        return {
            "ok": bool(receipt["ok"]),
            "verdict": receipt["verdict"],
            "stop_reason": receipt["stop_reason"],
            "epoch_dir": str(state.loop_dir),
            "epoch_digest": receipt["epoch_digest"],
            "wave_count": len(state.records),
            "wave_digests": list(state.child_digests),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_source": state.portfolio_source,
            "waves": state.records,
            "used_skill_route_discovery": receipt["used_skill_route_discovery"],
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }

    def wrap_refuse(exc: BaseException) -> BaseException:
        verdict = getattr(exc, "verdict", "refused")
        detail = getattr(exc, "detail", str(exc))
        return EpochRefused(str(verdict), str(detail))

    try:
        return le.run_durable_loop(
            dialect,
            max_rounds=max_waves,
            dispatch=dispatch,
            dispatch_budget=dispatch_budget,
            idle_limit=max(1, no_progress_limit),
            portfolio=portfolio,
            portfolio_dir=portfolio_dir,
            out_root=out_root,
            child_out_root=fleet_out_root,
            child_runner=runner,
            build_child_kwargs=build_child_kwargs,
            on_child_result=on_child_result,
            post_round_stop=post_round_stop,
            is_idle_round=is_idle,
            classify_verdict=classify,
            seal=seal,
            extract_dispatched=extract_dispatched,
            recompute_digest=_recompute_portfolio_digest,
            refuse_on_first=(uf.FleetRefused,),
            wrap_refuse=wrap_refuse,
        )
    except le.LoopRefused as exc:
        raise EpochRefused(exc.verdict, exc.detail) from exc


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def campaign_inject(target_dir: Path | str, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "target_dir": str(target_dir),
            "defect_ids": kwargs.get("defect_ids"),
            "stages": list(kwargs.get("stages") or []),
        }
        calls.append(payload)
        digest = _sha256_json(payload)
        camp_dir = scratch / "campaigns" / Path(str(target_dir)).name
        # Unique per call so digests differ across waves if same target re-hit.
        camp_dir = camp_dir / f"call-{len(calls):02d}"
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

    campaign_inject.calls = calls  # type: ignore[attr-defined]
    return campaign_inject


def builtin_upstream_epoch_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-wave epoch plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="epoch-proof-"))
    try:
        stew = scratch / "stewardship"
        stew.mkdir()

        # Three patch-bound targets → three campaignable actions.
        for name, version, defect in (
            ("alpha", "1.0.0", "alpha-dos"),
            ("beta", "2.0.0", "beta-xss"),
            ("gamma", "3.0.0", "gamma-redos"),
        ):
            uf._proof_target(
                stew,
                name=name,
                version=version,
                defects=[{
                    "id": defect,
                    "title": defect,
                    "kind": "complexity",
                    "patch": f"patches/{defect}.patch",
                    "repro": f"repros/{defect}.py",
                }],
            )
        # One empty frontier target → discover_empty (lower priority).
        uf._proof_target(stew, name="delta", version="4.0.0", defects=[])
        # One terminal success → done_merged (not campaignable).
        uf._proof_target(
            stew,
            name="epsilon",
            version="5.0.0",
            defects=[{
                "id": "epsilon-fixed",
                "title": "epsilon",
                "kind": "correctness",
                "patch": "patches/epsilon.patch",
                "repro": "repros/epsilon.py",
            }],
        )

        # Portfolio: epsilon already merged; alpha closed-unmerged → rework tops.
        portfolio = uf._proof_portfolio([
            {
                "name": "alpha",
                "version": "1.0.0",
                "defect_id": "alpha-dos",
                "outcome": "impact_closed_unmerged",
                "impact_digest": "a" * 64,
                "pr_number": 11,
                "ok": True,
            },
            {
                "name": "epsilon",
                "version": "5.0.0",
                "defect_id": "epsilon-fixed",
                "outcome": "impact_merged",
                "impact_digest": "b" * 64,
                "pr_number": 22,
                "ok": True,
            },
        ])

        campaign = _proof_campaign_runner(scratch)

        # 1) Multi-wave epoch: rework first, then other campaignables; feedback
        #    should retire each successful dispatch from the campaignable set.
        epoch = run_epoch(
            stewardship_root=stew,
            portfolio=portfolio,
            max_waves=5,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign,
            out_root=scratch / "epochs-progress",
        )
        multi_wave_ok = (
            epoch["ok"]
            and epoch["verdict"] == "epoch_progressed"
            and epoch["wave_count"] >= 3
            and epoch["total_dispatched_ok"] >= 3
            and epoch["portfolio_start_digest"] != epoch["portfolio_end_digest"]
        )
        # First wave top action should be rework on alpha.
        first_top = (epoch["waves"][0].get("top_action") or {}) if epoch["waves"] else {}
        rework_first = (
            first_top.get("action") == "rework_closed_unmerged"
            and first_top.get("name") == "alpha"
        )
        # After feedback, alpha should not remain campaignable in later waves.
        later_campaignable_names: list[str] = []
        for w in epoch["waves"][1:]:
            for d in w.get("dispatches") or []:
                later_campaignable_names.append(str(d.get("name") or ""))
        alpha_not_redispatched = "alpha" not in later_campaignable_names

        # Seal + verify.
        verified = verify_epoch_receipt(Path(epoch["epoch_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("wave_count") == epoch["wave_count"]

        # Tamper detection.
        epoch_path = Path(epoch["epoch_dir"]) / "epoch.json"
        receipt = json.loads(epoch_path.read_text(encoding="utf-8"))
        receipt["epoch_digest"] = "0" * 64
        epoch_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_epoch_receipt(Path(epoch["epoch_dir"]))
        tamper_detected = (
            not tampered["ok"] and "epoch_digest" in (tampered.get("mismatched") or [])
        )

        # 2) Idle epoch: only terminal outcomes → epoch_idle, zero dispatches.
        idle_stew = scratch / "idle-stew"
        idle_stew.mkdir()
        uf._proof_target(
            idle_stew,
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
        idle_portfolio = uf._proof_portfolio([{
            "name": "omega",
            "version": "9.0.0",
            "defect_id": "omega-merged",
            "outcome": "impact_merged",
            "impact_digest": "c" * 64,
            "ok": True,
        }])
        idle = run_epoch(
            stewardship_root=idle_stew,
            portfolio=idle_portfolio,
            max_waves=3,
            dispatch=True,
            campaign_runner=campaign,
            out_root=scratch / "epochs-idle",
        )
        idle_ok = (
            idle["ok"]
            and idle["verdict"] == "epoch_idle"
            and idle["stop_reason"] == "epoch_idle"
            and idle["total_dispatched"] == 0
            and idle["wave_count"] == 1
        )

        # 3) Budget stop: dispatch_budget=1 stops after one dispatch even if more work.
        campaign2 = _proof_campaign_runner(scratch / "budget")
        budgeted = run_epoch(
            stewardship_root=stew,
            portfolio=portfolio,
            max_waves=5,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign2,
            out_root=scratch / "epochs-budget",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
            and budgeted["total_dispatched_ok"] == 1
        )

        # 4) Rank-only: no dispatch, single wave.
        ranked = run_epoch(
            stewardship_root=stew,
            portfolio=portfolio,
            max_waves=3,
            dispatch=False,
            out_root=scratch / "epochs-ranked",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "epoch_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["wave_count"] == 1
            and ranked["total_dispatched"] == 0
            and (ranked["waves"][0].get("top_action") or {}).get("action")
            == "rework_closed_unmerged"
        )

        # 5) Custom feedback: map successful dispatch to impact_merged (terminal).
        def terminal_feedback(
            port: Mapping[str, Any] | None,
            disps: Sequence[Mapping[str, Any]],
            **_kw: Any,
        ) -> dict[str, Any]:
            return default_dispatch_feedback(
                port, disps, post_dispatch_outcome="impact_merged"
            )

        campaign3 = _proof_campaign_runner(scratch / "terminal")
        # Single campaignable target.
        one_stew = scratch / "one-stew"
        one_stew.mkdir()
        uf._proof_target(
            one_stew,
            name="zeta",
            version="1.0.0",
            defects=[{
                "id": "zeta-ready",
                "title": "zeta",
                "kind": "complexity",
                "patch": "patches/zeta.patch",
                "repro": "repros/zeta.py",
            }],
        )
        terminal = run_epoch(
            stewardship_root=one_stew,
            portfolio=None,
            max_waves=4,
            per_wave_dispatch_limit=1,
            dispatch=True,
            campaign_runner=campaign3,
            feedback_runner=terminal_feedback,
            out_root=scratch / "epochs-terminal",
        )
        # Wave 0 campaigns zeta; feedback → merged; wave 1 idle.
        term_receipt = json.loads(
            (Path(terminal["epoch_dir"]) / "epoch.json").read_text(encoding="utf-8")
        )
        final_entries = _portfolio_entries(term_receipt.get("portfolio_final"))
        terminal_ok = (
            terminal["ok"]
            and terminal["total_dispatched_ok"] == 1
            and terminal["wave_count"] >= 2
            and terminal["stop_reason"] == "epoch_idle"
            and any(
                e.get("defect_id") == "zeta-ready" and e.get("outcome") == "impact_merged"
                for e in final_entries
            )
        )

        # 6) Empty stewardship refuses.
        empty_root = scratch / "empty-stew"
        empty_root.mkdir()
        empty_refused = False
        try:
            run_epoch(
                stewardship_root=empty_root,
                dispatch=False,
                out_root=scratch / "epochs-empty",
            )
        except EpochRefused as exc:
            empty_refused = exc.verdict == "fleet_empty"

        # 7) max_waves stop with no_progress_limit high and feedback that does
        #    NOT retire work would loop; with default feedback budget caps waves.
        #    Explicit max_waves=2 with budget large stops at max_waves if work remains.
        campaign4 = _proof_campaign_runner(scratch / "maxw")
        # Feedback that does nothing → same campaignable every wave → no_progress.
        def noop_feedback(
            port: Mapping[str, Any] | None,
            _disps: Sequence[Mapping[str, Any]],
            **_kw: Any,
        ) -> dict[str, Any]:
            if port is None:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "entries": [],
                    "counts": {},
                    "portfolio_digest": _sha256_json({"entries": [], "counts": {}}),
                    "feedback_applied": [],
                }
            out = dict(port)
            out["feedback_applied"] = []
            return out

        stuck = run_epoch(
            stewardship_root=one_stew,
            portfolio=None,
            max_waves=5,
            per_wave_dispatch_limit=1,
            no_progress_limit=1,
            dispatch=True,
            campaign_runner=campaign4,
            feedback_runner=noop_feedback,
            out_root=scratch / "epochs-stuck",
        )
        # noop feedback: campaignable set unchanged → no_progress after wave(s).
        no_progress_ok = (
            stuck["ok"]
            and stuck["stop_reason"] == "no_progress"
            and stuck["wave_count"] >= 1
        )

        ok = all([
            multi_wave_ok,
            rework_first,
            alpha_not_redispatched,
            seal_ok,
            tamper_detected,
            idle_ok,
            budget_ok,
            rank_only_ok,
            terminal_ok,
            empty_refused,
            no_progress_ok,
        ])
        return {
            "ok": ok,
            "multi_wave_progressed": multi_wave_ok and rework_first and alpha_not_redispatched,
            "feedback_retires_work": alpha_not_redispatched and terminal_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "idle_short_circuits": idle_ok,
            "budget_stops": budget_ok,
            "rank_only": rank_only_ok,
            "terminal_feedback_idles": terminal_ok,
            "empty_refused": empty_refused,
            "no_progress_stops": no_progress_ok,
            "epoch_digest": epoch.get("epoch_digest"),
            "wave_count": epoch.get("wave_count"),
            "total_dispatched_ok": epoch.get("total_dispatched_ok"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a multi-wave fleet epoch and seal receipt")
    run_p.add_argument("--stewardship-root", type=Path, default=None)
    run_p.add_argument("--portfolio-dir", type=Path, default=None)
    run_p.add_argument("--max-waves", type=int, default=3)
    run_p.add_argument("--per-wave-dispatch-limit", type=int, default=1)
    run_p.add_argument("--dispatch-budget", type=int, default=None)
    run_p.add_argument("--no-progress-limit", type=int, default=1)
    run_p.add_argument(
        "--rank-only",
        action="store_true",
        help="plan/rank only; do not dispatch campaigns",
    )
    run_p.add_argument(
        "--assess-portfolio",
        action="store_true",
        help="assess live impact portfolio on wave 0 when no portfolio given",
    )
    run_p.add_argument("--out-root", type=Path, default=None)

    ver = sub.add_parser("verify", help="Verify a sealed epoch receipt")
    ver.add_argument("epoch_dir", type=Path)

    proof = sub.add_parser("proof", help="Run hermetic builtin proof")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "run":
        try:
            result = run_epoch(
                stewardship_root=args.stewardship_root,
                portfolio_dir=args.portfolio_dir,
                max_waves=args.max_waves,
                per_wave_dispatch_limit=args.per_wave_dispatch_limit,
                dispatch_budget=args.dispatch_budget,
                no_progress_limit=args.no_progress_limit,
                dispatch=not args.rank_only,
                assess_portfolio=args.assess_portfolio,
                out_root=args.out_root,
            )
        except EpochRefused as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 2
        # Compact output for CLI (waves can be large).
        compact = {k: v for k, v in result.items() if k != "waves"}
        compact["wave_summaries"] = [
            {
                "wave": w.get("wave"),
                "verdict": w.get("verdict"),
                "campaignable_count": w.get("campaignable_count"),
                "dispatched_ok": w.get("dispatched_ok"),
                "top_action": (w.get("top_action") or {}).get("action"),
                "fleet_digest": w.get("fleet_digest"),
            }
            for w in result.get("waves") or []
        ]
        print(json.dumps(compact, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify":
        result = verify_epoch_receipt(args.epoch_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "proof":
        result = builtin_upstream_epoch_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
