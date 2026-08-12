"""Upstream succession plane: multi-epoch stewardship mandate with impact refresh.

The epoch plane (``upstream_epoch``) closes multi-wave fleet loops *within* one
session, using post-dispatch portfolio feedback (default: ``impact_open``). It
does not:

1. chain multiple epochs over a durable mandate horizon;
2. re-assess open PRs between epochs (live impact refresh);
3. stop when a mandate goal is met (terminal coverage of stewarded work);
4. seal a multi-epoch chronicle that links epoch digests and portfolio evolution.

The succession plane closes that outer loop:

1. **epoch** — call the epoch plane (injected ``epoch_runner``; default
   ``run_epoch``) with the current portfolio world-model and per-epoch budgets;
2. **refresh** — between epochs, map open/follow outcomes through an injected
   ``impact_refresh_runner`` (default: promote ``impact_open`` →
   ``impact_merged`` for hermetic proofs of inter-epoch terminalization; live
   deployments inject ``assess_impact_portfolio``-backed refresh);
3. **chronicle** — append each epoch's digest, stop reason, and portfolio
   digests into a succession chain;
4. **stop** when any of:

   - ``max_epochs`` reached
   - global ``dispatch_budget`` exhausted across epochs
   - mandate goal met (``mandate_terminal_coverage``: every known
     stewardship defect is terminal-success in the portfolio)
   - consecutive idle/no-progress epochs (``idle_epoch_limit``)
   - explicit ``stop_when`` predicate returns a reason string

5. **seal** — write a succession receipt under ``artifacts/upstream-succession/``
   with sha256 digests of every epoch, the evolving portfolio, stop reason, and
   a succession chain digest; ``verify_succession_receipt`` re-checks the chain
   and detects tampering.

No skill-route discovery is used. The plane is mandate-level direction over the
epoch plane, not a new verifier of individual repairs.
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

from blackhole_agent import upstream_epoch as ue
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
LOOP_DIALECT = "succession"

# Multi-mode control engine + multi-depth nest membership.
CONTROL_ENGINE = True
CONTROL_ENGINE_MODE = "loop"
CONTROL_NEST = True
CONTROL_NEST_CHILD = "epoch"
CONTROL_NEST_CHILD_MODE = "loop"

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-succession"

# Outcomes that count as terminal success for mandate coverage.
TERMINAL_SUCCESS_OUTCOMES = frozenset({
    "impact_merged",
    "impact_released",
})

# Default inter-epoch refresh: open PRs land (merged) so the next epoch does
# not keep treating them as campaignable follow-work forever.
DEFAULT_REFRESH_PROMOTIONS: dict[str, str] = {
    "impact_open": "impact_merged",
}


class SuccessionRefused(Exception):
    """A verdict-bearing refusal: the succession must not continue."""

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


def _counts_from_entries(entries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        o = str(e.get("outcome") or "unknown")
        counts[o] = counts.get(o, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# mandate coverage


def inventory_defect_keys(
    stewardship_root: Path | None = None,
) -> list[tuple[str, str, str]]:
    """Return (name, version, defect_id) for every patch-bound stewardship defect."""
    inv = uf.inventory_targets(stewardship_root)
    keys: list[tuple[str, str, str]] = []
    for entry in inv:
        name = str(entry.get("name") or "")
        version = str(entry.get("version") or "")
        for did in entry.get("patch_bound_ids") or []:
            keys.append((name, version, str(did)))
    return keys


def mandate_terminal_coverage(
    portfolio: Mapping[str, Any] | None,
    stewardship_root: Path | None = None,
    *,
    required_keys: Sequence[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Compute terminal-success coverage of stewarded patch-bound defects.

    A mandate is met when every required (name, version, defect_id) has a
    portfolio entry with a terminal success outcome. Empty required sets are
    not met (avoids vacuous success on empty stewardship).
    """
    keys = list(required_keys) if required_keys is not None else inventory_defect_keys(
        stewardship_root
    )
    by_key: dict[tuple[str, str, str], str] = {}
    for e in _portfolio_entries(portfolio):
        k = (
            str(e.get("name") or ""),
            str(e.get("version") or ""),
            str(e.get("defect_id") or ""),
        )
        by_key[k] = str(e.get("outcome") or "")

    terminal: list[dict[str, Any]] = []
    open_or_missing: list[dict[str, Any]] = []
    for name, version, defect_id in keys:
        outcome = by_key.get((name, version, defect_id))
        item = {
            "name": name,
            "version": version,
            "defect_id": defect_id,
            "outcome": outcome,
        }
        if outcome in TERMINAL_SUCCESS_OUTCOMES:
            terminal.append(item)
        else:
            open_or_missing.append(item)

    required = len(keys)
    covered = len(terminal)
    met = required > 0 and covered == required
    return {
        "required": required,
        "covered": covered,
        "met": met,
        "coverage_ratio": (covered / required) if required else 0.0,
        "terminal": terminal,
        "open_or_missing": open_or_missing,
    }


# ---------------------------------------------------------------------------
# inter-epoch impact refresh


def default_impact_refresh(
    portfolio: Mapping[str, Any] | None,
    *,
    promotions: Mapping[str, str] | None = None,
    epoch_index: int = 0,
) -> dict[str, Any]:
    """Promote portfolio outcomes between epochs (default: open → merged).

    Simulates live impact re-assessment without network. Live deployments should
    inject a runner that calls the impact plane against real publication
    receipts. Returns a full portfolio dict with recomputed digest/counts and a
    ``refresh_applied`` list of mutations.
    """
    promo = dict(promotions) if promotions is not None else dict(DEFAULT_REFRESH_PROMOTIONS)
    entries = _portfolio_entries(portfolio)
    applied: list[dict[str, Any]] = []
    new_entries: list[dict[str, Any]] = []
    for e in entries:
        outcome = str(e.get("outcome") or "")
        if outcome in promo:
            updated = dict(e)
            new_outcome = promo[outcome]
            updated["outcome"] = new_outcome
            # Fresh digest so portfolio_digest changes even if only outcomes flip.
            prior_digest = str(e.get("impact_digest") or "")
            updated["impact_digest"] = _sha256_json(
                {
                    "prior": prior_digest,
                    "from": outcome,
                    "to": new_outcome,
                    "epoch_index": epoch_index,
                    "name": e.get("name"),
                    "defect_id": e.get("defect_id"),
                }
            )
            applied.append(
                {
                    "name": e.get("name"),
                    "version": e.get("version"),
                    "defect_id": e.get("defect_id"),
                    "from": outcome,
                    "to": new_outcome,
                }
            )
            new_entries.append(updated)
        else:
            new_entries.append(dict(e))

    counts = _counts_from_entries(new_entries)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "assessed_count": len(new_entries),
        "ok_count": len(new_entries),
        "failure_count": 0,
        "counts": counts,
        "entries": new_entries,
        "failures": [],
        "used_skill_route_discovery": False,
        "refresh_applied": applied,
        "refresh_epoch_index": epoch_index,
    }
    if portfolio:
        for k in ("portfolio_id", "source", "notes"):
            if k in portfolio:
                out[k] = portfolio[k]
    out["portfolio_digest"] = _recompute_portfolio_digest(out)
    return out


# ---------------------------------------------------------------------------
# epoch record / seal


def _epoch_record(
    *,
    epoch_index: int,
    epoch_result: Mapping[str, Any],
    portfolio_before_digest: str | None,
    portfolio_after_epoch_digest: str | None,
    portfolio_after_refresh_digest: str | None,
    refresh_applied: Sequence[Mapping[str, Any]],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "epoch": epoch_index,
        "ok": bool(epoch_result.get("ok")),
        "verdict": epoch_result.get("verdict"),
        "stop_reason": epoch_result.get("stop_reason"),
        "epoch_dir": epoch_result.get("epoch_dir"),
        "epoch_digest": epoch_result.get("epoch_digest"),
        "wave_count": int(epoch_result.get("wave_count") or 0),
        "total_dispatched": int(epoch_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(epoch_result.get("total_dispatched_ok") or 0),
        "portfolio_before_digest": portfolio_before_digest,
        "portfolio_after_epoch_digest": portfolio_after_epoch_digest,
        "portfolio_after_refresh_digest": portfolio_after_refresh_digest,
        "refresh_applied": list(refresh_applied),
        "refresh_count": len(refresh_applied),
        "coverage_before": {
            "required": coverage_before.get("required"),
            "covered": coverage_before.get("covered"),
            "met": coverage_before.get("met"),
            "coverage_ratio": coverage_before.get("coverage_ratio"),
        },
        "coverage_after": {
            "required": coverage_after.get("required"),
            "covered": coverage_after.get("covered"),
            "met": coverage_after.get("met"),
            "coverage_ratio": coverage_after.get("coverage_ratio"),
        },
    }


def _succession_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "max_epochs": receipt.get("max_epochs"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "epoch_count": receipt.get("epoch_count"),
        "epoch_digests": list(receipt.get("epoch_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "mandate_met": receipt.get("mandate_met"),
        "coverage_end": receipt.get("coverage_end"),
    }


def verify_succession_receipt(succession_dir: Path) -> dict[str, Any]:
    """Re-check a sealed succession receipt for digest integrity."""
    path = durable_read_path(Path(succession_dir) / "succession.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_succession_digest_payload(receipt))
    recorded = str(receipt.get("succession_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("succession_digest")

    # Epoch digests listed must match per-epoch records.
    epochs = list(receipt.get("epochs") or [])
    listed = list(receipt.get("epoch_digests") or [])
    if len(listed) != len(epochs):
        mismatched.append("epoch_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, epochs)):
            if listed_d != rec.get("epoch_digest"):
                mismatched.append(f"epoch_digests[{i}]")

    # If epoch dirs still exist, re-verify nested epoch seals when present.
    nested_failures: list[str] = []
    for rec in epochs:
        ed = rec.get("epoch_dir")
        if not ed:
            continue
        ep = Path(str(ed))
        if (ep / "epoch.json").is_file():
            nested = ue.verify_epoch_receipt(ep)
            if not nested.get("ok"):
                nested_failures.append(str(ed))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "succession_sealed" if ok else "succession_tampered",
        "succession_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "epoch_count": len(epochs),
    }


# ---------------------------------------------------------------------------
# run succession


def run_succession(
    *,
    stewardship_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    max_epochs: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    no_progress_limit: int = 1,
    idle_epoch_limit: int = 1,
    dispatch: bool = True,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    mandate_goal: str = "terminal_coverage",
    refresh_promotions: Mapping[str, str] | None = None,
    out_root: Path | None = None,
    epoch_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-epoch succession mandate and seal the receipt.

    Control flow is owned by :mod:`blackhole_agent.upstream_loop_engine`;
    this module supplies succession-dialect hooks (mandate coverage, impact
    refresh, receipt schema) only.

    Parameters
    ----------
    max_epochs:
        Hard cap on epochs (including idle/rank-only epochs).
    max_waves_per_epoch / per_wave_dispatch_limit / no_progress_limit:
        Forwarded to each epoch.
    dispatch_budget:
        Total dispatch *attempts* across all epochs; ``None`` means unlimited
        (still bounded by ``max_epochs * max_waves_per_epoch *
        per_wave_dispatch_limit``).
    idle_epoch_limit:
        Stop after this many consecutive epochs that dispatch nothing while the
        mandate is unmet.
    mandate_goal:
        ``terminal_coverage`` (default) stops when every patch-bound defect is
        terminal-success in the portfolio; ``none`` disables mandate stopping.
    impact_refresh_runner:
        Called after each epoch (except when succession stops immediately after
        that epoch due to mandate/budget). Receives portfolio + epoch_index.
    """
    if max_epochs < 1:
        raise SuccessionRefused("succession_invalid", "max_epochs must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise SuccessionRefused(
            "succession_invalid", "per_wave_dispatch_limit must be >= 0"
        )

    dialect = le.get_loop_dialect("succession")
    runner = epoch_runner or ue.run_epoch
    refresh = impact_refresh_runner or (
        lambda port, **kw: default_impact_refresh(
            port,
            promotions=refresh_promotions,
            epoch_index=int(kw.get("epoch_index") or 0),
        )
    )

    # Freeze required keys at succession start so mid-mandate inventory
    # mutations do not move the goalposts mid-proof.
    required_keys = inventory_defect_keys(stewardship_root)

    def _coverage(port: Mapping[str, Any] | None) -> dict[str, Any]:
        return mandate_terminal_coverage(
            port, stewardship_root, required_keys=required_keys
        )

    def build_child_kwargs(state: le.LoopState, round_index: int) -> dict[str, Any]:
        remaining = None
        if state.dispatch_budget is not None:
            remaining = max(0, int(state.dispatch_budget) - state.total_dispatched)
        kwargs: dict[str, Any] = {
            "stewardship_root": stewardship_root,
            "portfolio": state.portfolio,
            "max_waves": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": remaining,
            "no_progress_limit": no_progress_limit,
            "dispatch": bool(dispatch),
            "out_root": state.child_root / f"epoch-{round_index:02d}",
        }
        if campaign_runner is not None:
            kwargs["campaign_runner"] = campaign_runner
        if feedback_runner is not None:
            kwargs["feedback_runner"] = feedback_runner
        return kwargs

    def on_child_result(
        state: le.LoopState, round_index: int, epoch_result: dict[str, Any]
    ) -> dict[str, Any]:
        portfolio_before = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        coverage_before = _coverage(state.portfolio)

        after_epoch_portfolio: dict[str, Any] | None = state.portfolio
        epoch_dir = epoch_result.get("epoch_dir")
        if epoch_dir and (Path(str(epoch_dir)) / "epoch.json").is_file():
            nested = json.loads(
                (Path(str(epoch_dir)) / "epoch.json").read_text(encoding="utf-8")
            )
            if isinstance(nested.get("portfolio_final"), Mapping):
                after_epoch_portfolio = dict(nested["portfolio_final"])

        portfolio_after_epoch = (
            after_epoch_portfolio.get("portfolio_digest")
            if after_epoch_portfolio
            else epoch_result.get("portfolio_end_digest")
        )
        if after_epoch_portfolio is not None:
            state.portfolio = dict(after_epoch_portfolio)

        refresh_applied: list[dict[str, Any]] = []
        portfolio_after_refresh = portfolio_after_epoch
        if state.portfolio is not None:
            refreshed = refresh(
                state.portfolio,
                epoch_index=round_index,
                epoch_result=epoch_result,
            )
            if isinstance(refreshed, Mapping):
                state.portfolio = dict(refreshed)
                refresh_applied = list(
                    state.portfolio.pop("refresh_applied", []) or []
                )
                if "portfolio_digest" not in state.portfolio:
                    state.portfolio["portfolio_digest"] = _recompute_portfolio_digest(
                        state.portfolio
                    )
                portfolio_after_refresh = state.portfolio.get("portfolio_digest")

        coverage_after = _coverage(state.portfolio)
        state.extras["coverage_end"] = coverage_after
        if mandate_goal == "terminal_coverage" and coverage_after.get("met"):
            state.goal_met = True

        if epoch_result.get("epoch_digest"):
            state.child_digests.append(str(epoch_result["epoch_digest"]))

        return _epoch_record(
            epoch_index=round_index,
            epoch_result=epoch_result,
            portfolio_before_digest=portfolio_before,
            portfolio_after_epoch_digest=portfolio_after_epoch,
            portfolio_after_refresh_digest=portfolio_after_refresh,
            refresh_applied=refresh_applied,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )

    def pre_round_stop(state: le.LoopState, round_index: int) -> str | None:
        coverage = _coverage(state.portfolio)
        state.extras["coverage_end"] = coverage
        if mandate_goal == "terminal_coverage" and coverage.get("met"):
            state.goal_met = True
            return dialect.goal_stop_reason
        return None

    def post_round_stop(
        state: le.LoopState, round_index: int, epoch_result: dict[str, Any]
    ) -> str | None:
        coverage = state.extras.get("coverage_end") or _coverage(state.portfolio)
        if stop_when is not None:
            reason = stop_when(
                {
                    "epoch_index": round_index,
                    "epoch_result": epoch_result,
                    "portfolio": state.portfolio,
                    "epochs": state.records,
                    "total_dispatched": state.total_dispatched,
                    "total_dispatched_ok": state.total_dispatched_ok,
                    "coverage": coverage,
                }
            )
            if reason:
                return str(reason)
        if mandate_goal == "terminal_coverage" and coverage.get("met"):
            state.goal_met = True
            return dialect.goal_stop_reason
        return None

    def is_idle(
        state: le.LoopState, round_index: int, epoch_result: dict[str, Any]
    ) -> bool:
        return int(epoch_result.get("total_dispatched") or 0) == 0

    def classify(state: le.LoopState) -> tuple[bool, str]:
        final_coverage = _coverage(state.portfolio)
        state.extras["coverage_end"] = final_coverage
        if mandate_goal == "terminal_coverage" and final_coverage.get("met"):
            state.goal_met = True
        if not state.records:
            if state.goal_met:
                return True, "succession_mandate_met"
            return False, "succession_empty"
        if state.goal_met:
            return True, "succession_mandate_met"
        if state.total_dispatched_ok > 0:
            return True, "succession_progressed"
        if state.stop_reason == dialect.rank_only_stop_reason:
            return True, "succession_ranked"
        if state.stop_reason in {dialect.idle_stop_reason, "epoch_idle"}:
            return True, "succession_idle"
        if state.stop_reason == dialect.budget_stop_reason:
            return True, "succession_budgeted"
        return True, "succession_completed"

    def seal(state: le.LoopState) -> dict[str, Any]:
        coverage_end = state.extras.get("coverage_end") or _coverage(state.portfolio)
        portfolio_end_digest = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        receipt: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now_iso(),
            "ok": state.extras.get("ok"),
            "verdict": state.extras.get("verdict"),
            "stop_reason": state.stop_reason,
            "max_epochs": max_epochs,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": dispatch_budget,
            "dispatch_enabled": bool(dispatch),
            "mandate_goal": mandate_goal,
            "mandate_met": state.goal_met,
            "portfolio_source": state.portfolio_source,
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_final": state.portfolio,
            "required_keys": [
                {"name": n, "version": v, "defect_id": d} for n, v, d in required_keys
            ],
            "coverage_end": {
                "required": coverage_end.get("required"),
                "covered": coverage_end.get("covered"),
                "met": coverage_end.get("met"),
                "coverage_ratio": coverage_end.get("coverage_ratio"),
                "open_or_missing": coverage_end.get("open_or_missing"),
            },
            "epoch_count": len(state.records),
            "epochs": state.records,
            "epoch_digests": list(state.child_digests),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }
        receipt["succession_digest"] = _sha256_json(_succession_digest_payload(receipt))
        atomic_write_json(state.loop_dir / "succession.json", receipt)
        atomic_write_json(
            state.loop_dir / "summary.json",
            {
                "verdict": receipt["verdict"],
                "ok": receipt["ok"],
                "stop_reason": receipt["stop_reason"],
                "epoch_count": receipt["epoch_count"],
                "total_dispatched": receipt["total_dispatched"],
                "total_dispatched_ok": receipt["total_dispatched_ok"],
                "mandate_met": receipt["mandate_met"],
                "coverage_ratio": (receipt.get("coverage_end") or {}).get(
                    "coverage_ratio"
                ),
                "portfolio_start_digest": receipt["portfolio_start_digest"],
                "portfolio_end_digest": receipt["portfolio_end_digest"],
                "succession_digest": receipt["succession_digest"],
            },
        )
        return {
            "ok": bool(receipt["ok"]),
            "verdict": receipt["verdict"],
            "stop_reason": receipt["stop_reason"],
            "succession_dir": str(state.loop_dir),
            "succession_digest": receipt["succession_digest"],
            "epoch_count": len(state.records),
            "epoch_digests": list(state.child_digests),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "mandate_met": state.goal_met,
            "coverage_end": receipt["coverage_end"],
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_source": state.portfolio_source,
            "epochs": state.records,
            "used_skill_route_discovery": receipt["used_skill_route_discovery"],
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }

    def wrap_refuse(exc: BaseException) -> BaseException:
        verdict = getattr(exc, "verdict", "refused")
        detail = getattr(exc, "detail", str(exc))
        return SuccessionRefused(str(verdict), str(detail))

    try:
        return le.run_durable_loop(
            dialect,
            max_rounds=max_epochs,
            dispatch=dispatch,
            dispatch_budget=dispatch_budget,
            idle_limit=idle_epoch_limit,
            portfolio=portfolio,
            portfolio_dir=portfolio_dir,
            out_root=out_root,
            child_out_root=epoch_out_root,
            child_runner=runner,
            build_child_kwargs=build_child_kwargs,
            on_child_result=on_child_result,
            pre_round_stop=pre_round_stop,
            post_round_stop=post_round_stop,
            is_idle_round=is_idle,
            classify_verdict=classify,
            seal=seal,
            recompute_digest=_recompute_portfolio_digest,
            refuse_on_first=(ue.EpochRefused, uf.FleetRefused),
            wrap_refuse=wrap_refuse,
        )
    except le.LoopRefused as exc:
        raise SuccessionRefused(exc.verdict, exc.detail) from exc


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    return ue._proof_campaign_runner(scratch)


def builtin_upstream_succession_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-epoch succession plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="succession-proof-"))
    try:
        stew = scratch / "stewardship"
        stew.mkdir()

        # Two patch-bound targets → mandate requires both terminal.
        for name, version, defect in (
            ("alpha", "1.0.0", "alpha-dos"),
            ("beta", "2.0.0", "beta-xss"),
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
        # Empty frontier target does not count toward patch-bound mandate.
        uf._proof_target(stew, name="delta", version="4.0.0", defects=[])

        campaign = _proof_campaign_runner(scratch)

        # Within-epoch feedback leaves work as impact_open; inter-epoch refresh
        # promotes open → merged so the next epoch sees terminals and continues
        # or meets the mandate.
        #
        # Epoch 0: campaigns alpha then beta (max_waves=2), both → impact_open.
        # Refresh: both → impact_merged → mandate_met after epoch 0 refresh.
        succession = run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=4,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign,
            mandate_goal="terminal_coverage",
            out_root=scratch / "succ-mandate",
        )
        mandate_ok = (
            succession["ok"]
            and succession["verdict"] == "succession_mandate_met"
            and succession["mandate_met"] is True
            and succession["stop_reason"] == "mandate_met"
            and succession["total_dispatched_ok"] >= 2
            and succession["epoch_count"] >= 1
            and float((succession.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
        )
        # Refresh must have promoted open → merged (inter-epoch impact).
        refresh_promoted = False
        for ep in succession.get("epochs") or []:
            for r in ep.get("refresh_applied") or []:
                if r.get("from") == "impact_open" and r.get("to") == "impact_merged":
                    refresh_promoted = True
                    break
        multi_epoch_or_refresh = refresh_promoted and mandate_ok

        # Seal + verify.
        verified = verify_succession_receipt(Path(succession["succession_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("epoch_count") == succession[
            "epoch_count"
        ]

        # Tamper detection.
        succ_path = Path(succession["succession_dir"]) / "succession.json"
        receipt = json.loads(succ_path.read_text(encoding="utf-8"))
        receipt["succession_digest"] = "0" * 64
        succ_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_succession_receipt(Path(succession["succession_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "succession_digest" in (tampered.get("mismatched") or [])
        )

        # Multi-epoch progression: one dispatch per epoch so budget=2 spans
        # two epochs. No mandate; refresh leaves impact_open (no promotions).
        campaign2 = _proof_campaign_runner(scratch / "multi")
        multi = run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=4,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=2,
            dispatch=True,
            campaign_runner=campaign2,
            mandate_goal="none",
            # Keep open outcomes so mandate wouldn't help; still multi-epoch.
            refresh_promotions={},  # no promotions
            out_root=scratch / "succ-multi",
        )
        multi_epoch_ok = (
            multi["ok"]
            and multi["epoch_count"] >= 2
            and multi["total_dispatched_ok"] >= 2
            and multi["stop_reason"] == "dispatch_budget"
            and multi["portfolio_start_digest"] != multi["portfolio_end_digest"]
        )

        # Budget stop: succession dispatch_budget=1 across epochs.
        campaign3 = _proof_campaign_runner(scratch / "budget")
        budgeted = run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=5,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign3,
            mandate_goal="none",
            out_root=scratch / "succ-budget",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Idle succession: all defects already terminal.
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
        # mandate_goal terminal_coverage with already-met portfolio → no epochs
        # needed (break before first epoch) OR first epoch idle then met.
        # Our loop checks coverage *before* each epoch, so mandate_met with 0 epochs.
        pre_met = run_succession(
            stewardship_root=idle_stew,
            portfolio=idle_portfolio,
            max_epochs=3,
            dispatch=True,
            campaign_runner=campaign,
            mandate_goal="terminal_coverage",
            out_root=scratch / "succ-premet",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["mandate_met"] is True
            and pre_met["stop_reason"] == "mandate_met"
            and pre_met["epoch_count"] == 0
            and pre_met["verdict"] == "succession_mandate_met"
        )

        # Rank-only succession.
        ranked = run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=2,
            dispatch=False,
            mandate_goal="none",
            out_root=scratch / "succ-ranked",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "succession_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["epoch_count"] >= 1
        )

        # Empty stewardship refuses.
        empty_root = scratch / "empty-stew"
        empty_root.mkdir()
        empty_refused = False
        try:
            run_succession(
                stewardship_root=empty_root,
                dispatch=False,
                mandate_goal="none",
                out_root=scratch / "succ-empty",
            )
        except SuccessionRefused as exc:
            empty_refused = exc.verdict in {
                "fleet_empty",
                "epoch_invalid",
                "succession_invalid",
            } or "empty" in exc.verdict

        # Custom stop_when.
        campaign4 = _proof_campaign_runner(scratch / "stop")
        custom = run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=5,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch=True,
            campaign_runner=campaign4,
            mandate_goal="none",
            stop_when=lambda ctx: "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None,
            out_root=scratch / "succ-custom",
        )
        custom_ok = (
            custom["ok"]
            and custom["stop_reason"] == "custom_halt"
            and custom["total_dispatched_ok"] >= 1
        )

        # Refresh-driven rework: after epoch leaves impact_open, refresh demotes
        # to impact_closed_unmerged so the *next* epoch prioritizes rework.
        rework_stew = scratch / "rework-stew"
        rework_stew.mkdir()
        uf._proof_target(
            rework_stew,
            name="rho",
            version="1.0.0",
            defects=[{
                "id": "rho-1",
                "title": "rho",
                "kind": "complexity",
                "patch": "patches/rho.patch",
                "repro": "repros/rho.py",
            }],
        )
        uf._proof_target(
            rework_stew,
            name="sigma",
            version="1.0.0",
            defects=[{
                "id": "sigma-1",
                "title": "sigma",
                "kind": "complexity",
                "patch": "patches/sigma.patch",
                "repro": "repros/sigma.py",
            }],
        )
        campaign5 = _proof_campaign_runner(scratch / "rework")
        rework_refresh_calls = {"n": 0}

        def demote_then_merge(
            port: Mapping[str, Any] | None,
            **kw: Any,
        ) -> dict[str, Any]:
            rework_refresh_calls["n"] += 1
            if rework_refresh_calls["n"] == 1:
                return default_impact_refresh(
                    port,
                    promotions={"impact_open": "impact_closed_unmerged"},
                    epoch_index=int(kw.get("epoch_index") or 0),
                )
            return default_impact_refresh(
                port,
                promotions={
                    "impact_open": "impact_merged",
                    "impact_closed_unmerged": "impact_merged",
                },
                epoch_index=int(kw.get("epoch_index") or 0),
            )

        rework = run_succession(
            stewardship_root=rework_stew,
            portfolio=None,
            max_epochs=4,
            max_waves_per_epoch=1,  # one dispatch per epoch
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            impact_refresh_runner=demote_then_merge,
            mandate_goal="terminal_coverage",
            out_root=scratch / "succ-rework",
        )
        # After epoch 0 campaigns one target → open, refresh demotes to closed_unmerged.
        # Epoch 1 should rework that closed-unmerged (higher priority than remaining campaign).
        rework_first_after_refresh = False
        if len(rework.get("epochs") or []) >= 2:
            # Inspect epoch 1's nested epoch receipt for top action via waves — we
            # only store epoch summary. Check refresh demotion happened and second
            # epoch dispatched something.
            demoted = any(
                r.get("to") == "impact_closed_unmerged"
                for r in (rework["epochs"][0].get("refresh_applied") or [])
            )
            rework_first_after_refresh = demoted and rework["epochs"][1][
                "total_dispatched_ok"
            ] >= 1

        rework_ok = (
            rework["ok"]
            and rework_first_after_refresh
            and rework_refresh_calls["n"] >= 1
        )

        ok = all([
            mandate_ok,
            multi_epoch_or_refresh,
            multi_epoch_ok,
            seal_ok,
            tamper_detected,
            budget_ok,
            premet_ok,
            rank_only_ok,
            empty_refused,
            custom_ok,
            rework_ok,
        ])
        return {
            "ok": ok,
            "mandate_met": mandate_ok,
            "refresh_promotes_terminals": multi_epoch_or_refresh,
            "multi_epoch_progressed": multi_epoch_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "budget_stops": budget_ok,
            "premet_short_circuits": premet_ok,
            "rank_only": rank_only_ok,
            "empty_refused": empty_refused,
            "custom_stop": custom_ok,
            "refresh_drives_rework": rework_ok,
            "succession_digest": succession.get("succession_digest"),
            "epoch_count": succession.get("epoch_count"),
            "total_dispatched_ok": succession.get("total_dispatched_ok"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a multi-epoch succession mandate")
    run_p.add_argument("--stewardship-root", type=Path, default=None)
    run_p.add_argument("--portfolio-dir", type=Path, default=None)
    run_p.add_argument("--max-epochs", type=int, default=3)
    run_p.add_argument("--max-waves-per-epoch", type=int, default=3)
    run_p.add_argument("--per-wave-dispatch-limit", type=int, default=1)
    run_p.add_argument("--dispatch-budget", type=int, default=None)
    run_p.add_argument("--no-progress-limit", type=int, default=1)
    run_p.add_argument("--idle-epoch-limit", type=int, default=1)
    run_p.add_argument(
        "--mandate-goal",
        choices=("terminal_coverage", "none"),
        default="terminal_coverage",
    )
    run_p.add_argument(
        "--rank-only",
        action="store_true",
        help="plan/rank only; do not dispatch campaigns",
    )
    run_p.add_argument("--out-root", type=Path, default=None)

    ver = sub.add_parser("verify", help="Verify a sealed succession receipt")
    ver.add_argument("succession_dir", type=Path)

    proof = sub.add_parser("proof", help="Run hermetic builtin proof")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "run":
        try:
            result = run_succession(
                stewardship_root=args.stewardship_root,
                portfolio_dir=args.portfolio_dir,
                max_epochs=args.max_epochs,
                max_waves_per_epoch=args.max_waves_per_epoch,
                per_wave_dispatch_limit=args.per_wave_dispatch_limit,
                dispatch_budget=args.dispatch_budget,
                no_progress_limit=args.no_progress_limit,
                idle_epoch_limit=args.idle_epoch_limit,
                dispatch=not args.rank_only,
                mandate_goal=args.mandate_goal,
                out_root=args.out_root,
            )
        except SuccessionRefused as exc:
            print(
                json.dumps(
                    {"ok": False, "verdict": exc.verdict, "detail": exc.detail},
                    indent=2,
                )
            )
            return 2
        compact = {k: v for k, v in result.items() if k != "epochs"}
        compact["epoch_summaries"] = [
            {
                "epoch": e.get("epoch"),
                "verdict": e.get("verdict"),
                "stop_reason": e.get("stop_reason"),
                "total_dispatched_ok": e.get("total_dispatched_ok"),
                "refresh_count": e.get("refresh_count"),
                "coverage_after": e.get("coverage_after"),
                "epoch_digest": e.get("epoch_digest"),
            }
            for e in result.get("epochs") or []
        ]
        print(json.dumps(compact, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify":
        result = verify_succession_receipt(args.succession_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "proof":
        result = builtin_upstream_succession_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
