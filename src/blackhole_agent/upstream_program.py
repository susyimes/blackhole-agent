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
from blackhole_agent import upstream_loop_engine as le
from blackhole_agent import upstream_succession as us
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

# Owned by the multi-round durable loop engine (not a copy-paste tower).
# Program-dialect hooks still live here: surface expand, charter, ROI, resume.
LOOP_ENGINE = True
LOOP_ENGINE_NESTED = True  # children also engine-owned (succession → epoch)
LOOP_DIALECT = "program"

# Multi-mode control engine owns loop control flow.
CONTROL_ENGINE = True
CONTROL_ENGINE_MODE = "loop"

# Multi-depth control nest: program is the outer node of OPERATIONAL_NEST.
CONTROL_NEST = True
CONTROL_NEST_CHILD = "succession"
CONTROL_NEST_CHILD_MODE = "loop"
CONTROL_NEST_PATH = [
    {"mode": "loop", "dialect": "program", "max_rounds": 2, "idle_limit": 1},
    {"mode": "loop", "dialect": "succession", "max_rounds": 2, "idle_limit": 1},
    {"mode": "loop", "dialect": "epoch", "max_rounds": 2, "idle_limit": 1},
    {
        "mode": "pipeline",
        "dialect": "fleet",
        "stages": ["inventory", "portfolio", "rank", "dispatch"],
    },
]

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
    """Default expand: no new surface. Prefer ``surface_charter`` or an injected runner.

    Returns ``{"added_keys": [...], "detail": str, "expanded": bool}``.
    """
    return {
        "added_keys": [],
        "detail": "default_noop",
        "expanded": False,
        "succession_index": succession_index,
        "roi_hint": _roi_summary(roi_history),
    }


def normalize_surface_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a program surface charter into deterministic onboard entries.

    Each entry is ``{name, version, defects: [...], slug, entry_id}``. Defects
    must be patch-bound (``patch`` + ``repro``) so mandate re-derivation sees
    them after materialization.
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or "").strip()
        version = str(raw.get("version") or "").strip()
        if not name or not version:
            continue
        defects_in = list(raw.get("defects") or [])
        defects: list[dict[str, Any]] = []
        for d in defects_in:
            if not isinstance(d, Mapping):
                continue
            did = str(d.get("id") or "").strip()
            if not did:
                continue
            patch = str(d.get("patch") or f"patches/{did}.patch")
            repro = str(d.get("repro") or f"repros/{did}.py")
            defects.append(
                {
                    "id": did,
                    "title": str(d.get("title") or did),
                    "kind": str(d.get("kind") or "complexity"),
                    "patch": patch,
                    "repro": repro,
                }
            )
        if not defects:
            continue
        entry_id = str(raw.get("entry_id") or f"{name}@{version}")
        if entry_id in seen:
            continue
        seen.add(entry_id)
        out.append(
            {
                "entry_id": entry_id,
                "name": name,
                "version": version,
                "slug": f"{name}-{version}",
                "defects": defects,
                "kind": str(raw.get("kind") or "local_proof_target"),
            }
        )
    return out


def materialize_charter_entry(
    stewardship_root: Path,
    entry: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Materialize one charter entry onto the stewardship surface.

    Returns the patch-bound keys that became available (name/version/defect_id).
    """
    root = Path(stewardship_root)
    root.mkdir(parents=True, exist_ok=True)
    name = str(entry.get("name") or "")
    version = str(entry.get("version") or "")
    defects = list(entry.get("defects") or [])
    uf._proof_target(
        root,
        name=name,
        version=version,
        defects=defects,
    )
    return [
        {
            "name": name,
            "version": version,
            "defect_id": str(d.get("id") or ""),
        }
        for d in defects
        if d.get("id")
    ]


def make_charter_surface_expand(
    charter: Sequence[Mapping[str, Any]],
    *,
    only_when_covered: bool = True,
    max_entries_per_expand: int = 1,
    applied: Sequence[str] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Build a surface-expand runner from a durable program charter.

    Between successions the runner materializes the next unapplied charter
    entry onto ``stewardship_root`` (via :func:`materialize_charter_entry`).
    When ``only_when_covered`` is true (default), expansion waits until the
    current inventoried surface is terminal-covered — so each mandate wave
    completes before the charter grows. ROI history is recorded on the result
    for program learning; high mean efficiency can raise the batch size by one
    (capped by ``max_entries_per_expand + 1``).

    ``applied`` seeds already-materialized entry ids (resume continuity).
    """
    normalized = normalize_surface_charter(charter)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    # Also treat on-disk targets as applied so re-runs are idempotent.
    state = {
        "applied": applied_ids,
        "normalized": normalized,
        "only_when_covered": bool(only_when_covered),
        "max_entries_per_expand": max(1, int(max_entries_per_expand)),
    }

    def _runner(
        *,
        stewardship_root: Path | None,
        portfolio: Mapping[str, Any] | None,
        succession_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if stewardship_root is None:
            return {
                "added_keys": [],
                "detail": "charter_no_stewardship_root",
                "expanded": False,
                "charter_remaining": len(state["normalized"]) - len(state["applied"]),
                "charter_applied": sorted(state["applied"]),
            }
        root = Path(stewardship_root)
        # Sync applied from on-disk inventory (idempotent resume / re-entry).
        existing = {
            f"{n}@{v}"
            for n, v, _did in inventory_defect_keys(root)
        }
        for entry in state["normalized"]:
            eid = str(entry["entry_id"])
            slug_key = f"{entry['name']}@{entry['version']}"
            if slug_key in existing:
                state["applied"].add(eid)

        if state["only_when_covered"]:
            keys = inventory_defect_keys(root)
            # Empty surface with pending charter should expand immediately.
            if keys:
                cov = program_terminal_coverage(
                    portfolio, root, required_keys=keys
                )
                if not cov.get("met"):
                    return {
                        "added_keys": [],
                        "detail": "charter_wait_coverage",
                        "expanded": False,
                        "charter_remaining": len(
                            [e for e in state["normalized"] if e["entry_id"] not in state["applied"]]
                        ),
                        "charter_applied": sorted(state["applied"]),
                        "roi_hint": _roi_summary(roi_history),
                    }

        pending = [
            e for e in state["normalized"] if e["entry_id"] not in state["applied"]
        ]
        if not pending:
            return {
                "added_keys": [],
                "detail": "charter_exhausted",
                "expanded": False,
                "charter_remaining": 0,
                "charter_applied": sorted(state["applied"]),
                "roi_hint": _roi_summary(roi_history),
            }

        # ROI bias: strong mean efficiency unlocks one extra entry this expand.
        batch = state["max_entries_per_expand"]
        roi = _roi_summary(roi_history)
        if (
            float(roi.get("mean_coverage_delta") or 0.0) > 0.0
            and int(roi.get("total_dispatched_ok") or 0) > 0
        ):
            batch = min(batch + 1, len(pending))

        added_keys: list[dict[str, str]] = []
        applied_now: list[str] = []
        for entry in pending[:batch]:
            keys_added = materialize_charter_entry(root, entry)
            added_keys.extend(keys_added)
            state["applied"].add(str(entry["entry_id"]))
            applied_now.append(str(entry["entry_id"]))

        return {
            "added_keys": added_keys,
            "detail": "charter_materialize",
            "expanded": bool(added_keys),
            "charter_entries_applied": applied_now,
            "charter_remaining": len(
                [e for e in state["normalized"] if e["entry_id"] not in state["applied"]]
            ),
            "charter_applied": sorted(state["applied"]),
            "roi_hint": roi,
            "batch": batch,
        }

    # Expose mutable applied set for program-state persistence.
    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


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
    surface_charter: Sequence[Mapping[str, Any]] | None = None,
    charter_applied: Sequence[str] | None = None,
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
        "surface_charter": list(surface_charter or []),
        "charter_applied": list(charter_applied or []),
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
    surface_charter: Sequence[Mapping[str, Any]] | None = None,
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

    Control flow is owned by :mod:`blackhole_agent.upstream_loop_engine`;
    this module supplies program-dialect hooks (surface expand, charter, ROI,
    resume/persist, program goals) only.

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
    surface_charter:
        Optional durable list of future stewardship targets. When provided and
        ``surface_expand_runner`` is omitted, the program wires
        :func:`make_charter_surface_expand` so mandate waves re-open from the
        charter between successions. Charter progress is written into
        ``program_state.json`` for resume.
    resume_dir:
        Load ``program_state.json`` from a prior program dir and continue
        (portfolio, counters, roi_history, charter progress). New receipt is
        written under ``out_root`` (or a fresh stamp under the same parent).
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

    dialect = le.get_loop_dialect("program")
    runner = succession_runner or us.run_succession

    # Resume durable state if requested.
    prior_succession_count = 0
    roi_history: list[dict[str, Any]] = []
    succession_digests_prior: list[str] = []
    prior_total_dispatched = 0
    prior_total_dispatched_ok = 0
    resumed = False
    resume_program_id: str | None = None
    resumed_charter: list[dict[str, Any]] = []
    resumed_charter_applied: list[str] = []

    current_portfolio: dict[str, Any] | None = None
    portfolio_source = "none"
    if resume_dir is not None:
        prior_state = load_program_state(resume_dir)
        resumed = True
        resume_program_id = str(prior_state.get("program_id") or "") or None
        prior_succession_count = int(prior_state.get("succession_count") or 0)
        prior_total_dispatched = int(prior_state.get("total_dispatched") or 0)
        prior_total_dispatched_ok = int(prior_state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r)
            for r in (prior_state.get("roi_history") or [])
            if isinstance(r, Mapping)
        ]
        succession_digests_prior = [
            str(d) for d in (prior_state.get("succession_digests") or [])
        ]
        if isinstance(prior_state.get("portfolio"), Mapping):
            current_portfolio = dict(prior_state["portfolio"])
            portfolio_source = "resume"
        if isinstance(prior_state.get("surface_charter"), list):
            resumed_charter = [
                dict(e)
                for e in prior_state["surface_charter"]
                if isinstance(e, Mapping)
            ]
        if isinstance(prior_state.get("charter_applied"), list):
            resumed_charter_applied = [
                str(x) for x in prior_state["charter_applied"]
            ]
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

    # Surface expand: explicit runner wins; else charter (arg or resumed); else noop.
    active_charter = normalize_surface_charter(
        surface_charter if surface_charter is not None else resumed_charter
    )
    charter_expand: Callable[..., dict[str, Any]] | None = None
    if surface_expand_runner is not None:
        expand = surface_expand_runner
    elif active_charter:
        charter_expand = make_charter_surface_expand(
            active_charter,
            applied=resumed_charter_applied,
        )
        expand = charter_expand
    else:
        expand = default_surface_expand

    if current_portfolio and not current_portfolio.get("portfolio_digest"):
        current_portfolio["portfolio_digest"] = _recompute_portfolio_digest(
            current_portfolio
        )

    pid = (
        program_id
        or resume_program_id
        or f"program-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

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

    def _coverage(
        port: Mapping[str, Any] | None,
        *,
        required_keys: Sequence[tuple[str, str, str]] | None = None,
    ) -> dict[str, Any]:
        return program_terminal_coverage(
            port, stewardship_root, required_keys=required_keys
        )

    def _normalize_expand(expand_result: Any) -> dict[str, Any]:
        if not isinstance(expand_result, Mapping):
            expand_result = {
                "added_keys": [],
                "detail": "expand_invalid_return",
                "expanded": False,
            }
        expand_result = dict(expand_result)
        added_keys_raw = list(expand_result.get("added_keys") or [])
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
        return expand_result

    def _charter_applied_now(expand_result: Mapping[str, Any]) -> list[str]:
        if expand_result.get("charter_applied"):
            return [str(x) for x in expand_result["charter_applied"]]
        if charter_expand is not None and hasattr(charter_expand, "charter_state"):
            return sorted(
                str(x)
                for x in (charter_expand.charter_state.get("applied") or [])  # type: ignore[attr-defined]
            )
        return []

    def build_child_kwargs(state: le.LoopState, round_index: int) -> dict[str, Any]:
        succession_index = prior_succession_count + round_index
        remaining = None
        if state.dispatch_budget is not None:
            remaining = max(0, int(state.dispatch_budget) - state.total_dispatched)
        kwargs: dict[str, Any] = {
            "stewardship_root": stewardship_root,
            "portfolio": state.portfolio,
            "max_epochs": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": remaining,
            "no_progress_limit": no_progress_limit,
            "idle_epoch_limit": idle_epoch_limit,
            "dispatch": bool(dispatch),
            "mandate_goal": mandate_goal,
            "out_root": state.child_root / f"succession-{succession_index:02d}",
        }
        if campaign_runner is not None:
            kwargs["campaign_runner"] = campaign_runner
        if epoch_runner is not None:
            kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            kwargs["refresh_promotions"] = refresh_promotions
        return kwargs

    def on_child_result(
        state: le.LoopState, round_index: int, succ_result: dict[str, Any]
    ) -> dict[str, Any]:
        succession_index = prior_succession_count + round_index
        portfolio_before_digest = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        required_keys = inventory_defect_keys(stewardship_root)
        coverage_before = _coverage(state.portfolio, required_keys=required_keys)

        after_succ_portfolio: dict[str, Any] | None = state.portfolio
        succ_dir = succ_result.get("succession_dir")
        if succ_dir and (Path(str(succ_dir)) / "succession.json").is_file():
            nested = json.loads(
                (Path(str(succ_dir)) / "succession.json").read_text(encoding="utf-8")
            )
            if isinstance(nested.get("portfolio_final"), Mapping):
                after_succ_portfolio = dict(nested["portfolio_final"])
        if after_succ_portfolio is not None:
            state.portfolio = dict(after_succ_portfolio)
            if not state.portfolio.get("portfolio_digest"):
                state.portfolio["portfolio_digest"] = _recompute_portfolio_digest(
                    state.portfolio
                )

        # Surface expand between successions (even if mandate just met — new
        # frontier work may reopen the program).
        expand_result = _normalize_expand(
            expand(
                stewardship_root=stewardship_root,
                portfolio=state.portfolio,
                succession_index=succession_index,
                roi_history=list(state.extras.get("roi_history") or []),
            )
        )
        last_expand_added = len(list(expand_result.get("added_keys") or []))
        state.extras["last_expand_added"] = last_expand_added
        surface_expansions: list[dict[str, Any]] = list(
            state.extras.get("surface_expansions") or []
        )
        surface_expansions.append(
            {
                "after_succession": succession_index,
                "added_count": last_expand_added,
                "added_keys": list(expand_result.get("added_keys") or []),
                "detail": expand_result.get("detail"),
                "expanded": expand_result.get("expanded"),
                "charter_remaining": expand_result.get("charter_remaining"),
                "charter_entries_applied": expand_result.get(
                    "charter_entries_applied"
                ),
            }
        )
        state.extras["surface_expansions"] = surface_expansions

        required_after = inventory_defect_keys(stewardship_root)
        coverage_after = _coverage(state.portfolio, required_keys=required_after)
        state.extras["coverage_end"] = coverage_after

        roi_hist: list[dict[str, Any]] = list(state.extras.get("roi_history") or [])
        roi = score_succession_roi(
            succession_index=succession_index,
            succession_result=succ_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            surface_added=last_expand_added,
        )
        roi_hist.append(roi)
        state.extras["roi_history"] = roi_hist

        portfolio_after_digest = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        succ_digest = str(succ_result.get("succession_digest") or "")
        digests: list[str] = list(state.extras.get("succession_digests_acc") or [])
        if succ_digest:
            digests.append(succ_digest)
            state.child_digests.append(succ_digest)
        state.extras["succession_digests_acc"] = digests

        charter_applied_now = _charter_applied_now(expand_result)
        state.extras["charter_applied"] = charter_applied_now

        write_program_state(
            state.loop_dir,
            _state_payload(
                program_id=str(state.extras.get("program_id") or pid),
                succession_count=succession_index + 1,
                total_dispatched=state.total_dispatched,
                total_dispatched_ok=state.total_dispatched_ok,
                portfolio=state.portfolio,
                roi_history=roi_hist,
                required_keys=required_after,
                succession_digests=digests,
                stop_reason=None,
                program_goal=program_goal,
                surface_charter=active_charter,
                charter_applied=charter_applied_now,
            ),
        )

        if program_goal == "terminal_coverage" and coverage_after.get("met"):
            state.goal_met = True
        if (
            program_goal == "terminal_and_exhausted"
            and coverage_after.get("met")
            and last_expand_added == 0
        ):
            state.goal_met = True

        return _succession_record(
            succession_index=succession_index,
            succession_result=succ_result,
            portfolio_before_digest=portfolio_before_digest,
            portfolio_after_digest=portfolio_after_digest,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            surface_expand=expand_result,
            roi=roi,
        )

    def pre_round_stop(state: le.LoopState, round_index: int) -> str | None:
        coverage = _coverage(state.portfolio)
        state.extras["coverage_end"] = coverage
        if program_goal == "terminal_coverage" and coverage.get("met"):
            state.goal_met = True
            return dialect.goal_stop_reason
        if (
            program_goal == "terminal_and_exhausted"
            and coverage.get("met")
            and round_index > 0
            and int(state.extras.get("last_expand_added") or 0) == 0
        ):
            state.goal_met = True
            return dialect.goal_stop_reason
        return None

    def post_round_stop(
        state: le.LoopState, round_index: int, succ_result: dict[str, Any]
    ) -> str | None:
        coverage = state.extras.get("coverage_end") or _coverage(state.portfolio)
        last_expand_added = int(state.extras.get("last_expand_added") or 0)
        if stop_when is not None:
            reason = stop_when(
                {
                    "succession_index": prior_succession_count + round_index,
                    "succession_count": len(state.records),
                    "total_dispatched": state.total_dispatched,
                    "total_dispatched_ok": state.total_dispatched_ok,
                    "coverage": coverage,
                    "roi_history": list(state.extras.get("roi_history") or []),
                    "last_expand_added": last_expand_added,
                    "portfolio": state.portfolio,
                    "program_dir": str(state.loop_dir),
                }
            )
            if reason:
                return str(reason)
        if program_goal == "terminal_coverage" and coverage.get("met"):
            state.goal_met = True
            return dialect.goal_stop_reason
        if program_goal == "terminal_and_exhausted":
            if coverage.get("met") and last_expand_added == 0:
                state.goal_met = True
                return dialect.goal_stop_reason
        # Rank-only programs stop after one succession; do not mislabel as idle.
        if not state.dispatch:
            return dialect.rank_only_stop_reason
        return None

    def is_idle(
        state: le.LoopState, round_index: int, succ_result: dict[str, Any]
    ) -> bool:
        # New surface work re-opens the program; do not treat an expand as idle.
        if int(state.extras.get("last_expand_added") or 0) > 0:
            return False
        if (state.extras.get("coverage_end") or {}).get("met"):
            return False
        n = int(succ_result.get("total_dispatched") or 0)
        ok = int(succ_result.get("total_dispatched_ok") or 0)
        return n == 0 and ok == 0

    def classify(state: le.LoopState) -> tuple[bool, str]:
        final_keys = inventory_defect_keys(stewardship_root)
        coverage_end = _coverage(state.portfolio, required_keys=final_keys)
        state.extras["coverage_end"] = coverage_end
        state.extras["final_keys"] = final_keys
        last_expand_added = int(state.extras.get("last_expand_added") or 0)
        if program_goal == "terminal_coverage" and coverage_end.get("met"):
            state.goal_met = True
        if (
            program_goal == "terminal_and_exhausted"
            and coverage_end.get("met")
            and last_expand_added == 0
            and state.records
        ):
            state.goal_met = True

        stop_reason = state.stop_reason
        if state.goal_met and stop_reason in {
            dialect.goal_stop_reason,
            dialect.max_stop_reason,
        }:
            state.stop_reason = dialect.goal_stop_reason
            return True, "program_met"
        if stop_reason == dialect.rank_only_stop_reason:
            return True, "program_ranked"
        if stop_reason == dialect.idle_stop_reason:
            return True, "program_idle"
        if stop_reason == dialect.budget_stop_reason:
            return True, "program_budgeted"
        if stop_reason.startswith("succession_refused") or stop_reason.startswith(
            "fleet_refused"
        ):
            return False, "program_refused_mid"
        if state.goal_met:
            state.stop_reason = dialect.goal_stop_reason
            return True, "program_met"
        return True, "program_completed"

    def seal(state: le.LoopState) -> dict[str, Any]:
        final_keys = state.extras.get("final_keys") or inventory_defect_keys(
            stewardship_root
        )
        coverage_end = state.extras.get("coverage_end") or _coverage(
            state.portfolio, required_keys=final_keys
        )
        surface_expansions = list(state.extras.get("surface_expansions") or [])
        roi_hist = list(state.extras.get("roi_history") or [])
        roi_summary = _roi_summary(roi_hist)
        portfolio_end_digest = (
            state.portfolio.get("portfolio_digest") if state.portfolio else None
        )
        charter_applied = list(state.extras.get("charter_applied") or [])
        if active_charter and not charter_applied and charter_expand is not None:
            if hasattr(charter_expand, "charter_state"):
                charter_applied = sorted(
                    str(x)
                    for x in (charter_expand.charter_state.get("applied") or [])  # type: ignore[attr-defined]
                )

        receipt: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now_iso(),
            "ok": state.extras.get("ok"),
            "verdict": state.extras.get("verdict"),
            "stop_reason": state.stop_reason,
            "program_id": state.extras.get("program_id") or pid,
            "resumed": bool(state.extras.get("resumed")),
            "prior_succession_count": prior_succession_count,
            "max_successions": max_successions,
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": dispatch_budget,
            "dispatch_enabled": bool(dispatch),
            "program_goal": program_goal,
            "mandate_goal": mandate_goal,
            "program_met": state.goal_met,
            "portfolio_source": state.extras.get("portfolio_source")
            or state.portfolio_source,
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_final": state.portfolio,
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
            "succession_count": len(state.records),
            "successions": state.records,
            "succession_digests": [
                str(s.get("succession_digest") or "") for s in state.records
            ],
            "surface_expansions": surface_expansions,
            "surface_charter": active_charter,
            "charter_applied": charter_applied if active_charter else [],
            "roi_history": roi_hist,
            "roi_summary": roi_summary,
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }
        receipt["program_digest"] = _sha256_json(_program_digest_payload(receipt))
        atomic_write_json(state.loop_dir / "program.json", receipt)
        atomic_write_json(
            state.loop_dir / "summary.json",
            {
                "verdict": receipt["verdict"],
                "ok": receipt["ok"],
                "stop_reason": receipt["stop_reason"],
                "program_id": receipt["program_id"],
                "succession_count": receipt["succession_count"],
                "total_dispatched": receipt["total_dispatched"],
                "total_dispatched_ok": receipt["total_dispatched_ok"],
                "program_met": receipt["program_met"],
                "coverage_ratio": (receipt.get("coverage_end") or {}).get(
                    "coverage_ratio"
                ),
                "surface_expansion_count": sum(
                    1 for e in surface_expansions if e.get("added_count", 0) > 0
                ),
                "charter_size": len(active_charter),
                "charter_applied_count": len(receipt.get("charter_applied") or []),
                "portfolio_start_digest": receipt["portfolio_start_digest"],
                "portfolio_end_digest": receipt["portfolio_end_digest"],
                "program_digest": receipt["program_digest"],
                "resumed": receipt["resumed"],
                "loop_engine": True,
            },
        )

        write_program_state(
            state.loop_dir,
            _state_payload(
                program_id=str(receipt["program_id"]),
                succession_count=prior_succession_count + len(state.records),
                total_dispatched=state.total_dispatched,
                total_dispatched_ok=state.total_dispatched_ok,
                portfolio=state.portfolio,
                roi_history=roi_hist,
                required_keys=final_keys,
                succession_digests=receipt["succession_digests"],
                stop_reason=state.stop_reason,
                program_goal=program_goal,
                surface_charter=active_charter,
                charter_applied=list(receipt.get("charter_applied") or []),
            ),
        )

        return {
            "ok": bool(receipt["ok"]),
            "verdict": receipt["verdict"],
            "stop_reason": state.stop_reason,
            "program_dir": str(state.loop_dir),
            "program_digest": receipt["program_digest"],
            "program_id": receipt["program_id"],
            "succession_count": len(state.records),
            "succession_digests": list(receipt["succession_digests"]),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "program_met": state.goal_met,
            "coverage_end": receipt["coverage_end"],
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": portfolio_end_digest,
            "portfolio_source": receipt["portfolio_source"],
            "surface_expansions": surface_expansions,
            "surface_charter": active_charter,
            "charter_applied": list(receipt.get("charter_applied") or []),
            "roi_summary": roi_summary,
            "resumed": bool(receipt["resumed"]),
            "successions": state.records,
            "used_skill_route_discovery": receipt["used_skill_route_discovery"],
            "loop_engine": True,
            "loop_dialect": dialect.name,
        }

    def wrap_refuse(exc: BaseException) -> BaseException:
        if isinstance(exc, ProgramRefused):
            return exc
        verdict = getattr(exc, "verdict", "refused")
        detail = getattr(exc, "detail", str(exc))
        return ProgramRefused(str(verdict), str(detail))

    try:
        return le.run_durable_loop(
            dialect,
            max_rounds=max_successions,
            dispatch=dispatch,
            dispatch_budget=dispatch_budget,
            idle_limit=idle_succession_limit,
            portfolio=current_portfolio,
            out_root=program_dir,
            child_out_root=succ_root,
            child_runner=runner,
            build_child_kwargs=build_child_kwargs,
            on_child_result=on_child_result,
            pre_round_stop=pre_round_stop,
            post_round_stop=post_round_stop,
            is_idle_round=is_idle,
            classify_verdict=classify,
            seal=seal,
            recompute_digest=_recompute_portfolio_digest,
            prior_total_dispatched=prior_total_dispatched,
            prior_total_dispatched_ok=prior_total_dispatched_ok,
            refuse_on_first=(us.SuccessionRefused, uf.FleetRefused),
            wrap_refuse=wrap_refuse,
            nest_stamp=False,
            initial_extras={
                "resumed": resumed,
                "program_id": pid,
                "portfolio_source": portfolio_source,
                "roi_history": list(roi_history),
                "surface_expansions": [],
                "succession_digests_acc": list(succession_digests_prior),
                "last_expand_added": 0,
                "charter_applied": list(resumed_charter_applied),
            },
        )
    except le.LoopRefused as exc:
        raise ProgramRefused(exc.verdict, exc.detail) from exc


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

        # First-class surface charter: gamma materializes after alpha+beta terminal.
        surface_charter = [
            {
                "name": "gamma",
                "version": "3.0.0",
                "defects": [{
                    "id": "gamma-rce",
                    "title": "gamma",
                    "kind": "correctness",
                    "patch": "patches/gamma-rce.patch",
                    "repro": "repros/gamma-rce.py",
                }],
            }
        ]

        # Multi-succession with charter surface expansion → program_met.
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
            surface_charter=surface_charter,
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
        charter_expand_ok = (
            multi_succ_ok
            and any(
                e.get("detail") == "charter_materialize"
                for e in (program.get("surface_expansions") or [])
            )
            and "gamma@3.0.0" in (program.get("charter_applied") or [])
        )
        surface_expand_ok = charter_expand_ok

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
            charter_expand_ok,
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
            "charter_surface_expand": charter_expand_ok,
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
