"""Upstream program plane: multi-succession durable stewardship charter.

The succession plane (``upstream_succession``) closes multi-epoch mandates
*within one invocation*. It does not:

1. chain multiple successions under a durable multi-mandate program;
2. re-expand the stewardship surface between successions (frontier growth);
3. re-derive mandate scope after surface growth (goalposts may legitimately
   move when new patch-bound defects enter the program);
4. persist program state so a later process can resume the same charter;
5. score succession ROI to bias the next surface-expansion choice;
6. seal a multi-succession program chronicle linking succession digests.

The program plane closes that outer institutional loop:

1. **succession** — call the succession plane (injected ``succession_runner``;
   default ``run_succession``) with the current portfolio world-model and
   per-succession budgets;
2. **surface expand** — between successions, call an injected
   ``surface_expand_runner`` (default: no-op). Live deployments inject
   frontier-onboarding so new targets enter stewardship; hermetic proofs
   add patch-bound defects to the scratch surface;
3. **mandate re-derive** — re-inventory patch-bound defects after expansion;
   a previously-met mandate becomes open again when new defects appear;
4. **ROI score** — record per-succession coverage delta, dispatched_ok, and
   stop reason so expansion can prefer productive target classes;
5. **persist** — write ``program_state.json`` after every succession so a
   later ``run_program(..., resume_dir=...)`` continues the same charter;
6. **stop** when any of:

   - ``max_successions`` reached
   - global ``dispatch_budget`` exhausted across successions
   - program goal met (``terminal_and_exhausted``: every known patch-bound
     defect is terminal-success *and* surface expand returns no new keys)
   - consecutive idle/no-progress successions (``idle_succession_limit``)
   - explicit ``stop_when`` predicate returns a reason string

7. **seal** — write a program receipt under ``artifacts/upstream-program/``
   with sha256 digests of every succession, portfolio evolution, surface
   expansions, stop reason, and a program chain digest;
   ``verify_program_receipt`` re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is charter-level direction over
the succession plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_succession as us
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-program"

# Outcomes that count as terminal success for program coverage.
TERMINAL_SUCCESS_OUTCOMES = us.TERMINAL_SUCCESS_OUTCOMES


class ProgramRefused(Exception):
    """A verdict-bearing refusal: the program must not continue."""

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


def inventory_defect_keys(
    stewardship_root: Path | None = None,
) -> list[tuple[str, str, str]]:
    """Return (name, version, defect_id) for every patch-bound stewardship defect."""
    return us.inventory_defect_keys(stewardship_root)


def program_terminal_coverage(
    portfolio: Mapping[str, Any] | None,
    stewardship_root: Path | None = None,
    *,
    required_keys: Sequence[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Terminal-success coverage of all currently inventoried patch-bound defects."""
    return us.mandate_terminal_coverage(
        portfolio,
        stewardship_root,
        required_keys=required_keys,
    )


# ---------------------------------------------------------------------------
# surface expansion + ROI


def default_surface_expand(
    *,
    stewardship_root: Path | None,
    portfolio: Mapping[str, Any] | None,
    succession_index: int,
    roi_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Default expand: no new surface. Live deployments inject frontier onboarding.

    Returns ``{"added_keys": [...], "detail": str, "expanded": bool}``.
    """
    return {
        "added_keys": [],
        "detail": "default_noop",
        "expanded": False,
        "succession_index": succession_index,
        "roi_hint": _roi_summary(roi_history),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "successions": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "last_stop_reason": None,
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    return {
        "successions": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": mean_delta,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
    }


def score_succession_roi(
    *,
    succession_index: int,
    succession_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    surface_added: int,
) -> dict[str, Any]:
    """Score one succession for program-level learning / expansion bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    # Coverage ratio can drop when surface expands; also track absolute covered.
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    required_delta = int(coverage_after.get("required") or 0) - int(
        coverage_before.get("required") or 0
    )
    dispatched_ok = int(succession_result.get("total_dispatched_ok") or 0)
    stop_reason = str(succession_result.get("stop_reason") or "")
    # ROI: prefer absolute terminals gained per dispatch; expansion credit separate.
    efficiency = (
        (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    )
    return {
        "succession_index": succession_index,
        "stop_reason": stop_reason,
        "dispatched": int(succession_result.get("total_dispatched") or 0),
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "required_delta": required_delta,
        "surface_added": surface_added,
        "efficiency": efficiency,
        "mandate_met": bool(succession_result.get("mandate_met")),
        "succession_digest": succession_result.get("succession_digest"),
    }


# ---------------------------------------------------------------------------
# program state (durable resume)


def _state_payload(
    *,
    program_id: str,
    succession_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    required_keys: Sequence[tuple[str, str, str]],
    succession_digests: Sequence[str],
    stop_reason: str | None,
    program_goal: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "program_id": program_id,
        "updated_at": utc_now_iso(),
        "succession_count": succession_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "portfolio": dict(portfolio) if portfolio else None,
        "roi_history": list(roi_history),
        "required_keys": [
            {"name": n, "version": v, "defect_id": d} for n, v, d in required_keys
        ],
        "succession_digests": list(succession_digests),
        "stop_reason": stop_reason,
        "program_goal": program_goal,
    }


def write_program_state(program_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(program_dir) / "program_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_program_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "program_state.json")
    if not path.is_file():
        raise ProgramRefused("program_state_missing", f"no program_state.json under {resume_dir}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramRefused("program_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise ProgramRefused("program_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _succession_record(
    *,
    succession_index: int,
    succession_result: Mapping[str, Any],
    portfolio_before_digest: str | None,
    portfolio_after_digest: str | None,
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    surface_expand: Mapping[str, Any],
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "succession": succession_index,
        "ok": bool(succession_result.get("ok")),
        "verdict": succession_result.get("verdict"),
        "stop_reason": succession_result.get("stop_reason"),
        "succession_dir": succession_result.get("succession_dir"),
        "succession_digest": succession_result.get("succession_digest"),
        "epoch_count": int(succession_result.get("epoch_count") or 0),
        "total_dispatched": int(succession_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(succession_result.get("total_dispatched_ok") or 0),
        "mandate_met": bool(succession_result.get("mandate_met")),
        "portfolio_before_digest": portfolio_before_digest,
        "portfolio_after_digest": portfolio_after_digest,
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
        "surface_expand": {
            "expanded": bool(surface_expand.get("expanded")),
            "added_count": len(surface_expand.get("added_keys") or []),
            "added_keys": list(surface_expand.get("added_keys") or []),
            "detail": surface_expand.get("detail"),
        },
        "roi": dict(roi),
    }


def _program_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "program_id": receipt.get("program_id"),
        "program_goal": receipt.get("program_goal"),
        "max_successions": receipt.get("max_successions"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "succession_count": receipt.get("succession_count"),
        "succession_digests": list(receipt.get("succession_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "program_met": receipt.get("program_met"),
        "coverage_end": receipt.get("coverage_end"),
        "surface_expansions": receipt.get("surface_expansions"),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_program_receipt(program_dir: Path) -> dict[str, Any]:
    """Re-check a sealed program receipt for digest integrity."""
    path = durable_read_path(Path(program_dir) / "program.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_program_digest_payload(receipt))
    recorded = str(receipt.get("program_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("program_digest")

    successions = list(receipt.get("successions") or [])
    listed = list(receipt.get("succession_digests") or [])
    if len(listed) != len(successions):
        mismatched.append("succession_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, successions)):
            if listed_d != rec.get("succession_digest"):
                mismatched.append(f"succession_digests[{i}]")

    nested_failures: list[str] = []
    for rec in successions:
        sd = rec.get("succession_dir")
        if not sd:
            continue
        sp = Path(str(sd))
        if (sp / "succession.json").is_file():
            nested = us.verify_succession_receipt(sp)
            if not nested.get("ok"):
                nested_failures.append(str(sd))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "program_sealed" if ok else "program_tampered",
        "program_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "succession_count": len(successions),
    }


# ---------------------------------------------------------------------------
# run program


def run_program(
    *,
    stewardship_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    max_successions: int = 3,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    no_progress_limit: int = 1,
    idle_epoch_limit: int = 1,
    idle_succession_limit: int = 1,
    dispatch: bool = True,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    surface_expand_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    program_goal: str = "terminal_and_exhausted",
    mandate_goal: str = "terminal_coverage",
    refresh_promotions: Mapping[str, str] | None = None,
    program_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    succession_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-succession stewardship program and seal the receipt.

    Parameters
    ----------
    max_successions:
        Hard cap on successions (including idle/rank-only).
    max_epochs_per_succession / max_waves_per_epoch / per_wave_dispatch_limit:
        Forwarded to each succession.
    dispatch_budget:
        Total dispatch *attempts* across all successions; ``None`` means
        unlimited (still bounded by succession/epoch/wave caps).
    idle_succession_limit:
        Stop after this many consecutive successions that dispatch nothing
        while the program goal is unmet.
    program_goal:
        ``terminal_and_exhausted`` (default) stops when every patch-bound
        defect is terminal-success *and* the latest surface expand added
        nothing; ``terminal_coverage`` stops on coverage alone; ``none``
        disables program-goal stopping.
    mandate_goal:
        Forwarded to each succession (default ``terminal_coverage``).
    surface_expand_runner:
        Called after each succession (except when the program stops without
        needing expansion). Receives stewardship_root, portfolio,
        succession_index, roi_history.
    resume_dir:
        Load ``program_state.json`` from a prior program dir and continue
        (portfolio, counters, roi_history). New receipt is written under
        ``out_root`` (or a fresh stamp under the same parent).
    """
    if max_successions < 1:
        raise ProgramRefused("program_invalid", "max_successions must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise ProgramRefused(
            "program_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if program_goal not in {"terminal_and_exhausted", "terminal_coverage", "none"}:
        raise ProgramRefused(
            "program_invalid",
            f"unknown program_goal: {program_goal}",
        )

    runner = succession_runner or us.run_succession
    expand = surface_expand_runner or default_surface_expand

    # Resume durable state if requested.
    prior_succession_count = 0
    roi_history: list[dict[str, Any]] = []
    succession_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_program_id: str | None = None

    current_portfolio: dict[str, Any] | None = None
    portfolio_source = "none"
    if resume_dir is not None:
        state = load_program_state(resume_dir)
        resumed = True
        resume_program_id = str(state.get("program_id") or "") or None
        prior_succession_count = int(state.get("succession_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)]
        succession_digests = [str(d) for d in (state.get("succession_digests") or [])]
        if isinstance(state.get("portfolio"), Mapping):
            current_portfolio = dict(state["portfolio"])
            portfolio_source = "resume"
    elif portfolio is not None:
        current_portfolio = dict(portfolio)
        portfolio_source = "injected"
    elif portfolio_dir is not None:
        path = durable_read_path(Path(portfolio_dir) / "portfolio.json")
        if not path.is_file():
            raise ProgramRefused(
                "portfolio_missing", f"no portfolio.json under {portfolio_dir}"
            )
        current_portfolio = json.loads(path.read_text(encoding="utf-8"))
        portfolio_source = "dir"

    if current_portfolio and not current_portfolio.get("portfolio_digest"):
        current_portfolio["portfolio_digest"] = _recompute_portfolio_digest(
            current_portfolio
        )

    portfolio_start_digest = (
        current_portfolio.get("portfolio_digest") if current_portfolio else None
    )

    pid = program_id or resume_program_id or f"program-{utc_now_iso().replace(':', '').replace('-', '')}"

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        program_dir = Path(out_root)
        # If caller passed a dir that already sealed a program, nest a stamp.
        if (program_dir / "program.json").is_file():
            program_dir = program_dir / stamp
    else:
        program_dir = ARTIFACTS_ROOT / stamp
    program_dir.mkdir(parents=True, exist_ok=True)
    succ_root = (
        Path(succession_out_root)
        if succession_out_root
        else (program_dir / "successions")
    )

    successions: list[dict[str, Any]] = []
    surface_expansions: list[dict[str, Any]] = []
    stop_reason = "max_successions"
    idle_streak = 0
    program_met = False
    last_expand_added = 0
    coverage_end: dict[str, Any] = program_terminal_coverage(
        current_portfolio,
        stewardship_root,
    )

    for local_index in range(max_successions):
        succession_index = prior_succession_count + local_index
        portfolio_before_digest = (
            current_portfolio.get("portfolio_digest") if current_portfolio else None
        )
        required_keys = inventory_defect_keys(stewardship_root)
        coverage_before = program_terminal_coverage(
            current_portfolio,
            stewardship_root,
            required_keys=required_keys,
        )

        # Program-goal short-circuit before dispatching another succession.
        if program_goal == "terminal_coverage" and coverage_before.get("met"):
            stop_reason = "program_met"
            program_met = True
            coverage_end = coverage_before
            break
        if (
            program_goal == "terminal_and_exhausted"
            and coverage_before.get("met")
            and local_index > 0
            and last_expand_added == 0
        ):
            # Met coverage after a prior expand that added nothing (or start
            # with met + we already tried expand and got nothing).
            stop_reason = "program_met"
            program_met = True
            coverage_end = coverage_before
            break

        remaining_budget = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        succ_kwargs: dict[str, Any] = {
            "stewardship_root": stewardship_root,
            "portfolio": current_portfolio,
            "max_epochs": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": remaining_budget,
            "no_progress_limit": no_progress_limit,
            "idle_epoch_limit": idle_epoch_limit,
            "dispatch": bool(dispatch),
            "mandate_goal": mandate_goal,
            "out_root": succ_root / f"succession-{succession_index:02d}",
        }
        if campaign_runner is not None:
            succ_kwargs["campaign_runner"] = campaign_runner
        if epoch_runner is not None:
            succ_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            succ_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            succ_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            succ_kwargs["refresh_promotions"] = refresh_promotions

        try:
            succ_result = runner(**succ_kwargs)
        except us.SuccessionRefused as exc:
            if local_index == 0 and not resumed:
                raise ProgramRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"succession_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise ProgramRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(succ_result.get("total_dispatched") or 0)
        dispatched_ok = int(succ_result.get("total_dispatched_ok") or 0)
        total_dispatched += dispatched_n
        total_dispatched_ok += dispatched_ok

        # Pull portfolio_final from succession receipt when present.
        after_succ_portfolio: dict[str, Any] | None = current_portfolio
        succ_dir = succ_result.get("succession_dir")
        if succ_dir and (Path(str(succ_dir)) / "succession.json").is_file():
            receipt = json.loads(
                (Path(str(succ_dir)) / "succession.json").read_text(encoding="utf-8")
            )
            if isinstance(receipt.get("portfolio_final"), Mapping):
                after_succ_portfolio = dict(receipt["portfolio_final"])
        if after_succ_portfolio is not None:
            current_portfolio = dict(after_succ_portfolio)
            if not current_portfolio.get("portfolio_digest"):
                current_portfolio["portfolio_digest"] = _recompute_portfolio_digest(
                    current_portfolio
                )

        coverage_mid = program_terminal_coverage(
            current_portfolio,
            stewardship_root,
            required_keys=required_keys,
        )

        # Surface expand between successions (even if mandate just met — new
        # frontier work may reopen the program).
        expand_result = expand(
            stewardship_root=stewardship_root,
            portfolio=current_portfolio,
            succession_index=succession_index,
            roi_history=roi_history,
        )
        if not isinstance(expand_result, Mapping):
            expand_result = {
                "added_keys": [],
                "detail": "expand_invalid_return",
                "expanded": False,
            }
        expand_result = dict(expand_result)
        added_keys_raw = list(expand_result.get("added_keys") or [])
        # Normalize added keys to dicts.
        added_keys: list[dict[str, str]] = []
        for k in added_keys_raw:
            if isinstance(k, Mapping):
                added_keys.append(
                    {
                        "name": str(k.get("name") or ""),
                        "version": str(k.get("version") or ""),
                        "defect_id": str(k.get("defect_id") or ""),
                    }
                )
            elif isinstance(k, (list, tuple)) and len(k) == 3:
                added_keys.append(
                    {"name": str(k[0]), "version": str(k[1]), "defect_id": str(k[2])}
                )
        expand_result["added_keys"] = added_keys
        expand_result["expanded"] = bool(
            expand_result.get("expanded") or len(added_keys) > 0
        )
        last_expand_added = len(added_keys)
        surface_expansions.append(
            {
                "after_succession": succession_index,
                "added_count": last_expand_added,
                "added_keys": added_keys,
                "detail": expand_result.get("detail"),
                "expanded": expand_result.get("expanded"),
            }
        )

        # Re-derive mandate after surface growth.
        required_after = inventory_defect_keys(stewardship_root)
        coverage_after = program_terminal_coverage(
            current_portfolio,
            stewardship_root,
            required_keys=required_after,
        )

        roi = score_succession_roi(
            succession_index=succession_index,
            succession_result=succ_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            surface_added=last_expand_added,
        )
        roi_history.append(roi)

        portfolio_after_digest = (
            current_portfolio.get("portfolio_digest") if current_portfolio else None
        )
        succ_digest = str(succ_result.get("succession_digest") or "")
        if succ_digest:
            succession_digests.append(succ_digest)

        rec = _succession_record(
            succession_index=succession_index,
            succession_result=succ_result,
            portfolio_before_digest=portfolio_before_digest,
            portfolio_after_digest=portfolio_after_digest,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            surface_expand=expand_result,
            roi=roi,
        )
        successions.append(rec)

        # Persist durable state after each succession for resume.
        state = _state_payload(
            program_id=pid,
            succession_count=succession_index + 1,
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            portfolio=current_portfolio,
            roi_history=roi_history,
            required_keys=required_after,
            succession_digests=succession_digests,
            stop_reason=None,
            program_goal=program_goal,
        )
        write_program_state(program_dir, state)

        coverage_end = coverage_after

        # New surface work re-opens the program; do not treat an expand as idle.
        if last_expand_added > 0:
            idle_streak = 0
        elif dispatched_ok == 0 and dispatched_n == 0:
            idle_streak += 1
        else:
            idle_streak = 0

        # Custom stop.
        if stop_when is not None:
            reason = stop_when(
                {
                    "succession_index": succession_index,
                    "succession_count": len(successions),
                    "total_dispatched": total_dispatched,
                    "total_dispatched_ok": total_dispatched_ok,
                    "coverage": coverage_after,
                    "roi_history": roi_history,
                    "last_expand_added": last_expand_added,
                    "portfolio": current_portfolio,
                    "program_dir": str(program_dir),
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Program goal after this succession + expand.
        if program_goal == "terminal_coverage" and coverage_after.get("met"):
            stop_reason = "program_met"
            program_met = True
            break
        if program_goal == "terminal_and_exhausted":
            if coverage_after.get("met") and last_expand_added == 0:
                stop_reason = "program_met"
                program_met = True
                break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        # Rank-only programs stop after one succession; do not mislabel as idle.
        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_succession_limit and not coverage_after.get("met"):
            stop_reason = "program_idle"
            break
    else:
        stop_reason = "max_successions"

    # Final coverage snapshot.
    final_keys = inventory_defect_keys(stewardship_root)
    coverage_end = program_terminal_coverage(
        current_portfolio,
        stewardship_root,
        required_keys=final_keys,
    )
    if program_goal == "terminal_coverage" and coverage_end.get("met"):
        program_met = True
    if (
        program_goal == "terminal_and_exhausted"
        and coverage_end.get("met")
        and last_expand_added == 0
        and successions
    ):
        program_met = True

    portfolio_end_digest = (
        current_portfolio.get("portfolio_digest") if current_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)

    if program_met and stop_reason in {"program_met", "max_successions"}:
        verdict = "program_met"
        ok = True
        stop_reason = "program_met"
    elif stop_reason == "rank_only":
        verdict = "program_ranked"
        ok = True
    elif stop_reason == "program_idle":
        verdict = "program_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "program_budgeted"
        ok = True
    elif stop_reason.startswith("succession_refused") or stop_reason.startswith(
        "fleet_refused"
    ):
        verdict = "program_refused_mid"
        ok = False
    else:
        verdict = "program_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "program_id": pid,
        "resumed": resumed,
        "prior_succession_count": prior_succession_count,
        "max_successions": max_successions,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "program_goal": program_goal,
        "mandate_goal": mandate_goal,
        "program_met": program_met,
        "portfolio_source": portfolio_source,
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "portfolio_final": current_portfolio,
        "required_keys": [
            {"name": n, "version": v, "defect_id": d} for n, v, d in final_keys
        ],
        "coverage_end": {
            "required": coverage_end.get("required"),
            "covered": coverage_end.get("covered"),
            "met": coverage_end.get("met"),
            "coverage_ratio": coverage_end.get("coverage_ratio"),
            "open_or_missing": coverage_end.get("open_or_missing"),
        },
        "succession_count": len(successions),
        "successions": successions,
        "succession_digests": [
            s.get("succession_digest") for s in successions if s.get("succession_digest")
        ],
        "surface_expansions": surface_expansions,
        "roi_history": roi_history,
        "roi_summary": roi_summary,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    # Align succession_digests with records for seal integrity.
    receipt["succession_digests"] = [
        str(s.get("succession_digest") or "") for s in successions
    ]
    receipt["program_digest"] = _sha256_json(_program_digest_payload(receipt))
    atomic_write_json(program_dir / "program.json", receipt)
    atomic_write_json(
        program_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "program_id": receipt["program_id"],
            "succession_count": receipt["succession_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "program_met": receipt["program_met"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "surface_expansion_count": sum(
                1 for e in surface_expansions if e.get("added_count", 0) > 0
            ),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "program_digest": receipt["program_digest"],
            "resumed": resumed,
        },
    )

    # Final durable state with stop reason.
    write_program_state(
        program_dir,
        _state_payload(
            program_id=pid,
            succession_count=prior_succession_count + len(successions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            portfolio=current_portfolio,
            roi_history=roi_history,
            required_keys=final_keys,
            succession_digests=receipt["succession_digests"],
            stop_reason=stop_reason,
            program_goal=program_goal,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "program_dir": str(program_dir),
        "program_digest": receipt["program_digest"],
        "program_id": pid,
        "succession_count": len(successions),
        "succession_digests": list(receipt["succession_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "program_met": program_met,
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "portfolio_source": portfolio_source,
        "surface_expansions": surface_expansions,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "successions": successions,
        "used_skill_route_discovery": receipt["used_skill_route_discovery"],
    }


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    return us._proof_campaign_runner(scratch)


def builtin_upstream_program_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-succession program plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="program-proof-"))
    try:
        stew = scratch / "stewardship"
        stew.mkdir()

        # Initial surface: two patch-bound targets.
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

        campaign = _proof_campaign_runner(scratch)

        # Surface expand once after succession 0: add gamma when alpha+beta done.
        expand_calls = {"n": 0}

        def expand_once(
            *,
            stewardship_root: Path | None,
            portfolio: Mapping[str, Any] | None,
            succession_index: int,
            roi_history: Sequence[Mapping[str, Any]],
        ) -> dict[str, Any]:
            expand_calls["n"] += 1
            # After first succession that terminal-covers the initial surface,
            # onboard gamma. Subsequent expands are no-ops.
            keys = inventory_defect_keys(stewardship_root)
            has_gamma = any(k[0] == "gamma" for k in keys)
            cov = program_terminal_coverage(
                portfolio, stewardship_root, required_keys=keys
            )
            if not has_gamma and cov.get("met"):
                uf._proof_target(
                    Path(stewardship_root) if stewardship_root else stew,
                    name="gamma",
                    version="3.0.0",
                    defects=[{
                        "id": "gamma-rce",
                        "title": "gamma",
                        "kind": "correctness",
                        "patch": "patches/gamma-rce.patch",
                        "repro": "repros/gamma-rce.py",
                    }],
                )
                return {
                    "added_keys": [
                        {
                            "name": "gamma",
                            "version": "3.0.0",
                            "defect_id": "gamma-rce",
                        }
                    ],
                    "detail": "frontier_onboard_gamma",
                    "expanded": True,
                }
            return {
                "added_keys": [],
                "detail": "noop",
                "expanded": False,
            }

        # Multi-succession with surface expansion → program_met.
        program = run_program(
            stewardship_root=stew,
            portfolio=None,
            max_successions=4,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=8,
            dispatch=True,
            campaign_runner=campaign,
            surface_expand_runner=expand_once,
            program_goal="terminal_and_exhausted",
            mandate_goal="terminal_coverage",
            out_root=scratch / "prog-mandate",
        )
        multi_succ_ok = (
            program["ok"]
            and program["program_met"] is True
            and program["stop_reason"] == "program_met"
            and program["succession_count"] >= 2
            and program["total_dispatched_ok"] >= 3
            and float((program.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
            and any(
                e.get("added_count", 0) > 0 for e in (program.get("surface_expansions") or [])
            )
        )
        surface_expand_ok = multi_succ_ok and expand_calls["n"] >= 2

        # Seal + verify.
        verified = verify_program_receipt(Path(program["program_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("succession_count") == program[
            "succession_count"
        ]

        # Tamper detection.
        prog_path = Path(program["program_dir"]) / "program.json"
        receipt = json.loads(prog_path.read_text(encoding="utf-8"))
        receipt["program_digest"] = "0" * 64
        prog_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_program_receipt(Path(program["program_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "program_digest" in (tampered.get("mismatched") or [])
        )

        # Multi-succession progression without expand (budget spans successions).
        stew2 = scratch / "stew2"
        stew2.mkdir()
        for name, version, defect in (
            ("delta", "1.0.0", "delta-1"),
            ("epsilon", "1.0.0", "epsilon-1"),
        ):
            uf._proof_target(
                stew2,
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
        campaign2 = _proof_campaign_runner(scratch / "multi")
        multi = run_program(
            stewardship_root=stew2,
            portfolio=None,
            max_successions=4,
            max_epochs_per_succession=1,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=2,
            dispatch=True,
            campaign_runner=campaign2,
            surface_expand_runner=default_surface_expand,
            program_goal="none",
            mandate_goal="none",
            # Keep open outcomes; no promotions → multi-succession work.
            refresh_promotions={},
            out_root=scratch / "prog-multi",
        )
        multi_succession_ok = (
            multi["ok"]
            and multi["succession_count"] >= 2
            and multi["total_dispatched_ok"] >= 2
            and multi["stop_reason"] == "dispatch_budget"
            and multi["portfolio_start_digest"] != multi["portfolio_end_digest"]
        )

        # Budget stop.
        campaign3 = _proof_campaign_runner(scratch / "budget")
        budgeted = run_program(
            stewardship_root=stew2,
            portfolio=None,
            max_successions=5,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign3,
            program_goal="none",
            mandate_goal="none",
            out_root=scratch / "prog-budget",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit: all terminal + no expand → program_met with
        # zero successions when goal is terminal_coverage.
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
        pre_met = run_program(
            stewardship_root=idle_stew,
            portfolio=idle_portfolio,
            max_successions=3,
            dispatch=True,
            campaign_runner=campaign,
            program_goal="terminal_coverage",
            mandate_goal="terminal_coverage",
            out_root=scratch / "prog-premet",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["program_met"] is True
            and pre_met["stop_reason"] == "program_met"
            and pre_met["succession_count"] == 0
            and pre_met["verdict"] == "program_met"
        )

        # Rank-only program.
        ranked = run_program(
            stewardship_root=stew2,
            portfolio=None,
            max_successions=2,
            dispatch=False,
            program_goal="none",
            mandate_goal="none",
            out_root=scratch / "prog-ranked",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "program_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["succession_count"] >= 1
        )

        # Empty stewardship refuses.
        empty_root = scratch / "empty-stew"
        empty_root.mkdir()
        empty_refused = False
        try:
            run_program(
                stewardship_root=empty_root,
                dispatch=False,
                program_goal="none",
                mandate_goal="none",
                out_root=scratch / "prog-empty",
            )
        except ProgramRefused as exc:
            empty_refused = exc.verdict in {
                "fleet_empty",
                "epoch_invalid",
                "succession_invalid",
                "program_invalid",
            } or "empty" in exc.verdict

        # Custom stop_when.
        campaign4 = _proof_campaign_runner(scratch / "stop")
        custom = run_program(
            stewardship_root=stew2,
            portfolio=None,
            max_successions=5,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch=True,
            campaign_runner=campaign4,
            program_goal="none",
            mandate_goal="none",
            stop_when=lambda ctx: "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None,
            out_root=scratch / "prog-custom",
        )
        custom_ok = (
            custom["ok"]
            and custom["stop_reason"] == "custom_halt"
            and custom["total_dispatched_ok"] >= 1
        )

        # Durable resume: run partial program (budget=1), resume with more budget.
        stew3 = scratch / "stew3"
        stew3.mkdir()
        for name, version, defect in (
            ("zeta", "1.0.0", "zeta-1"),
            ("eta", "1.0.0", "eta-1"),
        ):
            uf._proof_target(
                stew3,
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
        campaign5 = _proof_campaign_runner(scratch / "resume-a")
        partial = run_program(
            stewardship_root=stew3,
            portfolio=None,
            max_successions=1,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign5,
            program_goal="none",
            mandate_goal="none",
            program_id="resume-proof",
            out_root=scratch / "prog-partial",
        )
        state_path = Path(partial["program_dir"]) / "program_state.json"
        state_exists = state_path.is_file()
        campaign6 = _proof_campaign_runner(scratch / "resume-b")
        resumed = run_program(
            stewardship_root=stew3,
            resume_dir=Path(partial["program_dir"]),
            max_successions=2,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            # Global budget continues from prior total_dispatched.
            dispatch_budget=3,
            dispatch=True,
            campaign_runner=campaign6,
            program_goal="none",
            mandate_goal="none",
            out_root=scratch / "prog-resumed",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["program_id"] == "resume-proof"
            and resumed["total_dispatched_ok"] >= partial["total_dispatched_ok"]
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring produces non-empty history on multi-succession program.
        roi_ok = (
            isinstance(program.get("roi_summary"), Mapping)
            and int((program["roi_summary"] or {}).get("successions") or 0) >= 2
            and int((program["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
        )

        ok = all([
            multi_succ_ok,
            surface_expand_ok,
            seal_ok,
            tamper_detected,
            multi_succession_ok,
            budget_ok,
            premet_ok,
            rank_only_ok,
            empty_refused,
            custom_ok,
            resume_ok,
            roi_ok,
        ])
        return {
            "ok": ok,
            "program_met": multi_succ_ok,
            "surface_expand_reopens_mandate": surface_expand_ok,
            "multi_succession_progressed": multi_succession_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "budget_stops": budget_ok,
            "premet_short_circuits": premet_ok,
            "rank_only": rank_only_ok,
            "empty_refused": empty_refused,
            "custom_stop": custom_ok,
            "durable_resume": resume_ok,
            "roi_scored": roi_ok,
            "program_digest": program.get("program_digest"),
            "succession_count": program.get("succession_count"),
            "total_dispatched_ok": program.get("total_dispatched_ok"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a multi-succession stewardship program")
    run_p.add_argument("--stewardship-root", type=Path, default=None)
    run_p.add_argument("--portfolio-dir", type=Path, default=None)
    run_p.add_argument("--max-successions", type=int, default=3)
    run_p.add_argument("--max-epochs-per-succession", type=int, default=3)
    run_p.add_argument("--max-waves-per-epoch", type=int, default=3)
    run_p.add_argument("--per-wave-dispatch-limit", type=int, default=1)
    run_p.add_argument("--dispatch-budget", type=int, default=None)
    run_p.add_argument("--no-progress-limit", type=int, default=1)
    run_p.add_argument("--idle-epoch-limit", type=int, default=1)
    run_p.add_argument("--idle-succession-limit", type=int, default=1)
    run_p.add_argument(
        "--program-goal",
        choices=("terminal_and_exhausted", "terminal_coverage", "none"),
        default="terminal_and_exhausted",
    )
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
    run_p.add_argument("--resume-dir", type=Path, default=None)
    run_p.add_argument("--program-id", type=str, default=None)
    run_p.add_argument("--out-root", type=Path, default=None)

    ver = sub.add_parser("verify", help="Verify a sealed program receipt")
    ver.add_argument("program_dir", type=Path)

    proof = sub.add_parser("proof", help="Run hermetic builtin proof")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "run":
        try:
            result = run_program(
                stewardship_root=args.stewardship_root,
                portfolio_dir=args.portfolio_dir,
                max_successions=args.max_successions,
                max_epochs_per_succession=args.max_epochs_per_succession,
                max_waves_per_epoch=args.max_waves_per_epoch,
                per_wave_dispatch_limit=args.per_wave_dispatch_limit,
                dispatch_budget=args.dispatch_budget,
                no_progress_limit=args.no_progress_limit,
                idle_epoch_limit=args.idle_epoch_limit,
                idle_succession_limit=args.idle_succession_limit,
                dispatch=not args.rank_only,
                program_goal=args.program_goal,
                mandate_goal=args.mandate_goal,
                resume_dir=args.resume_dir,
                program_id=args.program_id,
                out_root=args.out_root,
            )
        except ProgramRefused as exc:
            print(
                json.dumps(
                    {"ok": False, "verdict": exc.verdict, "detail": exc.detail},
                    indent=2,
                )
            )
            return 2
        compact = {k: v for k, v in result.items() if k != "successions"}
        compact["succession_summaries"] = [
            {
                "succession": s.get("succession"),
                "verdict": s.get("verdict"),
                "stop_reason": s.get("stop_reason"),
                "total_dispatched_ok": s.get("total_dispatched_ok"),
                "mandate_met": s.get("mandate_met"),
                "surface_added": (s.get("surface_expand") or {}).get("added_count"),
                "succession_digest": s.get("succession_digest"),
            }
            for s in result.get("successions") or []
        ]
        print(json.dumps(compact, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify":
        result = verify_program_receipt(args.program_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "proof":
        result = builtin_upstream_program_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
