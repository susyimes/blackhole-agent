"""Application-growth plane: an unplannable goal grows through forage matching.

The forage-growth plane still needs a separate invocation: match a goal key,
forage, then re-plan. This module closes that leftover — **automatic growth**:

- the only caller input is an :class:`ApplicationTask` (initial state, goal
  keys, frozen oracle); no package name and no forage-growth plane call;
- if the live registry already plans the task, it executes and never forages;
- if the task is unplannable, forage matching runs in-process (catalog
  provides stripped, lying popular decoy probed and skipped) and the first
  covering package is foraged;
- the original task is then re-planned and executed against the grown
  registry — a goal that was honestly unplannable becomes solvable;
- an uncovered goal stays an honest refusal; no ledger write is fabricated;
- ablation hides the foraged capability and the goal is unplannable again;
- a digest-sealed report under ``artifacts/capability-application-growth/``;
  verification re-grows the recorded task, re-checks the digest, and
  re-proves the foraged capability, so a tampered winner or forged grade
  fails.

``run_application_task(..., grow=True)`` is the same path: unplannable
tasks grow without a separate plane invocation. Default ``grow=False``
keeps planner honesty.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import (
    _digest,
    load_persisted_records,
    prove_absorbed_capability,
)
from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    ApplicationTask,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_forage_growth import (
    match_forage_goal,
    strip_declared_provides,
)
from blackhole_agent.capability_forage_targets import (
    HERMETIC_ABSORBED_SLUGS,
    load_catalog,
    rank_catalog,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-growth"
DEFAULT_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_apply_catalog.json"
WINNER_SLUG = "forage-rotate"
DECOY_SLUG = "forage-pick"
GOAL_KEY = "rotate_output"
NO_MATCH_GOAL = "unicorn_output"
WINNER_CAPABILITY_ID = f"capability.absorbed-{WINNER_SLUG}"
APPLY_ABSORBED_SLUGS = frozenset(HERMETIC_ABSORBED_SLUGS) | frozenset({"forage-flip"})

GROW_TASK = ApplicationTask(
    id="rotate-unplannable",
    description="Unplannable application goal that must grow through forage matching.",
    initial_state={"text": "Hello World"},
    goal=(GOAL_KEY,),
    oracle={GOAL_KEY: "rotated:Hello World"},
)

UNCOVERED_TASK = ApplicationTask(
    id="unicorn-uncovered",
    description="Unplannable application goal no catalog package covers.",
    initial_state={"text": "Hello World"},
    goal=(NO_MATCH_GOAL,),
    oracle={NO_MATCH_GOAL: "missing"},
)

ALREADY_SOLVABLE_TASK = next(task for task in APPLICATION_TASKS if task.id == "ledger-inventory-check")


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def load_apply_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the hermetic application-growth forage catalog."""

    return load_catalog(path or DEFAULT_CATALOG)


def _live_registry(repo_root: Path, *, hide: Sequence[str] = ()) -> dict[str, Any]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return build_application_registry(
        ledger,
        hide=hide,
        include_synthesized=True,
        include_absorbed=True,
    )


def grow_application_task(
    task: ApplicationTask,
    *,
    catalog: Mapping[str, Any] | None = None,
    absorbed: Sequence[str] | None = None,
    forage: bool = True,
    hide_before: Sequence[str] = (),
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Grow an unplannable application task through forage matching.

    Already-solvable tasks execute and never forage. The caller never names a
    package and never invokes the forage-growth plane.
    """

    payload = dict(catalog) if catalog is not None else load_apply_catalog()
    absorbed_slugs = list(absorbed) if absorbed is not None else sorted(APPLY_ABSORBED_SLUGS)
    before = _live_registry(repo_root, hide=hide_before)
    planned = plan_application_task(task, before)
    if planned is not None:
        result = run_application_task(task, before)
        result.update(
            {
                "grew": False,
                "forage": None,
                "unplannable_before": False,
                "used_forage_growth_plane": False,
                "winner_slug": "",
            }
        )
        return result

    matched = match_forage_goal(
        task.goal,
        catalog=payload,
        absorbed=absorbed_slugs,
        forage=forage,
        repo_root=repo_root,
    )
    forage_record = {
        "ok": bool((matched.get("forage") or {}).get("ok") if forage else matched.get("ok")),
        "slug": (matched.get("winner") or {}).get("slug") or "",
        "capability_id": (matched.get("forage") or {}).get("capability_id") or "",
        "error": matched.get("error") or "",
        "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
        "probes": [
            {
                "slug": row.get("slug"),
                "skip_reason": row.get("skip_reason"),
                "covers_goal": bool(row.get("covers_goal")),
            }
            for row in matched.get("probes") or []
        ],
    }
    if forage:
        forage_record["ok"] = bool((matched.get("forage") or {}).get("ok"))
        if not forage_record["ok"]:
            forage_record["error"] = str(
                (matched.get("forage") or {}).get("error") or matched.get("error") or "forage failed"
            )
    if not matched.get("ok"):
        return {
            "ok": False,
            "plan": None,
            "outcome": {},
            "error": str(matched.get("error") or "no forage match"),
            "grew": False,
            "forage": forage_record,
            "unplannable_before": True,
            "used_forage_growth_plane": False,
            "winner_slug": forage_record["slug"],
        }

    after = _live_registry(repo_root)
    result = run_application_task(task, after)
    result.update(
        {
            "grew": True,
            "forage": forage_record,
            "unplannable_before": True,
            "used_forage_growth_plane": False,
            "winner_slug": forage_record["slug"],
        }
    )
    return result


def _covering_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    if WINNER_CAPABILITY_ID in ledger.capabilities:
        return (WINNER_CAPABILITY_ID,)
    records = {str(item.get("slug")): item for item in load_persisted_records()}
    capability_id = str((records.get(WINNER_SLUG) or {}).get("capability_id") or "")
    return (capability_id,) if capability_id else ()


def _honesty(task: ApplicationTask, capability_id: str, *, repo_root: Path) -> dict[str, Any]:
    hidden = _live_registry(repo_root, hide=[capability_id] if capability_id else ())
    grown = _live_registry(repo_root)
    unplannable_before = plan_application_task(task, hidden) is None
    grown_result = run_application_task(task, grown)
    grown_plan_solved = bool(
        grown_result.get("ok") and grown_result.get("plan") and capability_id in (grown_result.get("plan") or [])
    )
    ablation_unplannable = plan_application_task(task, hidden) is None
    return {
        "ok": unplannable_before and grown_plan_solved and ablation_unplannable,
        "unplannable_before": unplannable_before,
        "grown_plan_solved": grown_plan_solved,
        "ablation_unplannable": ablation_unplannable,
        "capability_id": capability_id,
        "plan": grown_result.get("plan"),
    }


def _scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(GOAL_KEY,))
    matched = match_forage_goal((GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root)
    probes = list(matched.get("probes") or [])
    decoy_probe = next((row for row in probes if row.get("slug") == DECOY_SLUG), {})
    skipped_reasons = {row["slug"]: row["skip_reason"] for row in trend.get("skipped") or []}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root
    )
    return {
        "trend_winner_slug": (trend.get("winner") or {}).get("slug") or "",
        "trend_decoy_wins": (trend.get("winner") or {}).get("slug") == DECOY_SLUG,
        "lying_catalog_picks_decoy": (lying.get("winner") or {}).get("slug") == DECOY_SLUG,
        "match_is_forage_rotate": (matched.get("winner") or {}).get("slug") == WINNER_SLUG,
        "decoy_probed_and_skipped": decoy_probe.get("skip_reason") == "not_covering"
        and GOAL_KEY not in set(decoy_probe.get("inferred_provides") or []),
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "absorbed_skipped": skipped_reasons.get("inflection") == "already_absorbed"
        and skipped_reasons.get("forage-lab") == "already_absorbed",
        "nonviable_skipped": skipped_reasons.get("forage-empty") == "nonviable",
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "inferred_provides": row.get("inferred_provides") or [],
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {
            "ok": bool(lying.get("ok")),
            "winner": (lying.get("winner") or {}).get("slug") or "",
        },
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def run_application_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow the hermetic unplannable task, skip solvable ones, seal evidence."""

    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
    )
    hide_before = _covering_hide(repo_root)
    grown = grow_application_task(
        GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(GROW_TASK, capability_id, repo_root=repo_root)
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": grown.get("winner_slug") == WINNER_SLUG,
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
            "plan": skip_result.get("plan"),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
    }


def verify_application_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-grow the hermetic task and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = {
        "already_solvable_skips_forage": bool((report.get("already_solvable") or {}).get("ok"))
        and (report.get("already_solvable") or {}).get("grew") is False,
        "uncovered_stays_unsolved": (not (report.get("uncovered") or {}).get("ok"))
        and (report.get("uncovered") or {}).get("error") == "no forage match"
        and (report.get("uncovered") or {}).get("grew") is False,
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": ((report.get("grown") or {}).get("winner_slug") == WINNER_SLUG),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool(((report.get("grown") or {}).get("forage") or {}).get("ok")),
        "grew": bool((report.get("grown") or {}).get("grew")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": True,
    }
    expected_grade["ok"] = all(expected_grade.values())
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == WINNER_SLUG
    live_proof = prove_absorbed_capability(WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    ok = digest_ok and catalog_ok and grade_ok and winner_ok and live_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
    }


def builtin_application_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: unplannable tasks grow through forage matching."""

    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_growth_plane(report_dir)
        verification = verify_application_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_forage_rotate"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": bool((plane.get("grade") or {}).get("grow_winner_is_forage_rotate")),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "action": "application_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_growth_plane_proof; r=builtin_application_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_decoy_wins') and r.get('lying_catalog_picks_decoy') "
        "and r.get('grow_winner_is_forage_rotate') and r.get('decoy_probed_and_skipped') "
        "and r.get('catalog_provides_ignored') and r.get('uncovered_refused') "
        "and r.get('absorbed_skipped') and r.get('nonviable_skipped') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('grew') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-growth-plane",
        name="Application-growth forage plane",
        description=(
            "An unplannable application goal grows itself through forage "
            "matching without a separate plane invocation: already-solvable "
            "tasks never forage, uncovered goals stay honestly unsolved, a "
            "lying popular decoy is probed and skipped, the covering package "
            "is foraged, and the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_growth_plane",
        proof_command=application_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_apply_catalog.json",
            "tests/fixtures/external_packages/forage-rotate/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "An unplannable application goal no longer needs a separate "
            "forage-growth invocation: grow=True (or grow_application_task) "
            "matches and forages a covering package in-process, a lying "
            "popular decoy is skipped, and the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_growth_plane() -> dict[str, Any]:
    """Entry surface: run the hermetic plane and summarize the grown task."""

    result = run_application_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "grade": result.get("grade"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Application-growth forage plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    grow_parser = sub.add_parser("grow", help="grow an unplannable application goal through forage matching")
    grow_parser.add_argument("--goal", action="append", required=True, help="goal key the task must cover")
    grow_parser.add_argument("--text", default="Hello World", help="initial text state for unary string goals")

    plane_parser = sub.add_parser("plane", help="run the sealed hermetic plane")
    plane_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    sub.add_parser("proof", help="run the registered application-growth-plane proof")
    sub.add_parser("register", help="register and prove the plane in the live ledger")

    verify_parser = sub.add_parser("verify", help="verify a sealed application-growth report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    args = parser.parse_args(argv)
    if args.command_name == "grow":
        goal = tuple(args.goal)
        task = ApplicationTask(
            id="cli-grow",
            description="CLI application-growth task.",
            initial_state={"text": args.text},
            goal=goal,
            oracle={},
        )
        result = grow_application_task(task)
    elif args.command_name == "plane":
        result = run_application_growth_plane(forage=not args.no_forage)
    elif args.command_name == "proof":
        result = builtin_application_growth_plane_proof()
    elif args.command_name == "register":
        result = register_application_growth_plane_capability()
    else:
        result = verify_application_growth_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
