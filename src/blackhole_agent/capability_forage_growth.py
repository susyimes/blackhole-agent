"""Forage-growth plane: an unsolved goal forages a matching package.

The forage-target plane still ranks catalog ``provides`` that a human wrote.
A lying annotation can therefore pick a popular decoy that cannot solve the
goal. This module closes that leftover — **goal-driven matching**:

- an unsolved goal key is the only caller input besides a registry catalog;
  no package name is supplied;
- catalog ``provides`` are stripped before ranking, so a lying annotation
  cannot pick the winner;
- remaining candidates are ranked by recorded downloads only;
- each ranked candidate is probed through foraging inference (no ledger
  write) until inferred provides cover the goal;
- the first covering candidate is foraged; non-covering candidates are
  skipped, never absorbed;
- a goal no candidate covers is an honest ``no forage match`` refusal;
- a goal that was honestly unplannable becomes solvable after the forage
  and unplannable again under ablation;
- a digest-sealed report under ``artifacts/capability-forage-growth/``;
  verification re-matches the recorded catalog, re-checks the digest, and
  re-proves the foraged capability, so a tampered winner or forged grade
  fails.

The hermetic catalog is a frozen payload whose popular decoy *declares*
the goal key and whose actual callable does not. Live registry search is
not the registered proof.
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
from blackhole_agent.capability_forage_targets import (
    HERMETIC_ABSORBED_SLUGS,
    forage_request_for,
    load_catalog,
    rank_catalog,
)
from blackhole_agent.capability_foraging import forage_package, infer_acquisition_spec

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-forage-growth"
DEFAULT_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_growth_catalog.json"
WINNER_SLUG = "forage-flip"
DECOY_SLUG = "forage-pick"
GOAL_KEY = "flip_output"
NO_MATCH_GOAL = "unicorn_output"


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def load_growth_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the hermetic goal-driven forage catalog."""

    return load_catalog(path or DEFAULT_CATALOG)


def strip_declared_provides(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Drop human-authored provides so ranking cannot see catalog lies."""

    stripped: list[dict[str, Any]] = []
    for item in items:
        entry = dict(item)
        entry["provides"] = []
        stripped.append(entry)
    return stripped


def probe_candidate(
    entry: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    live_fetch: bool = False,
) -> dict[str, Any]:
    """Infer provided keys from the package itself. Never writes the ledger."""

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=live_fetch)
    slug = str(request.get("slug") or "")
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return {
            "ok": False,
            "slug": slug,
            "inferred_provides": [],
            "callables": [],
            "covers_goal": False,
            "skip_reason": "no_source",
            "error": f"forage source missing: {source}",
        }
    with tempfile.TemporaryDirectory(prefix=f"blackhole-forage-probe-{slug}-") as tmp:
        inference = infer_acquisition_spec(
            slug=slug,
            name=str(request["name"]),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request["name"]),
            origin=request.get("origin") or {},
            runtime=str(request.get("runtime") or ""),
            bundle=True,
        )
    if not inference.get("ok"):
        return {
            "ok": False,
            "slug": slug,
            "inferred_provides": [],
            "callables": [],
            "covers_goal": False,
            "skip_reason": "inference_failed",
            "error": str(inference.get("error") or "inference failed"),
        }
    specs = [inference["spec"], *list(inference.get("bundle_specs") or [])]
    provides: list[str] = []
    callables: list[str] = []
    for spec in specs:
        key = str(spec.provides)
        if key and key not in provides:
            provides.append(key)
        callables.append(str(spec.callable_name))
    return {
        "ok": True,
        "slug": slug,
        "inferred_provides": provides,
        "callables": callables,
        "covers_goal": False,
        "skip_reason": "",
        "error": "",
        "runtime": (inference.get("record") or {}).get("runtime"),
        "runtime_deps": list((inference.get("record") or {}).get("runtime_deps") or []),
        "extra_paths": list((inference.get("record") or {}).get("extra_paths") or []),
        "default_export": bool((inference.get("record") or {}).get("default_export")),
        "default_export_object": bool((inference.get("record") or {}).get("default_export_object")),
        "default_export_class": bool((inference.get("record") or {}).get("default_export_class")),
        "default_export_class_static": bool(
            (inference.get("record") or {}).get("default_export_class_static")
        ),
        "named_export_class_static": bool(
            (inference.get("record") or {}).get("named_export_class_static")
        ),
        "nested_namespace_class_static": bool(
            (inference.get("record") or {}).get("nested_namespace_class_static")
        ),
    }


def _covers(probe: Mapping[str, Any], goal_keys: Sequence[str]) -> bool:
    inferred = {str(item) for item in probe.get("inferred_provides") or []}
    goals = {str(item) for item in goal_keys}
    return bool(probe.get("ok") and goals and goals <= inferred)


def match_forage_goal(
    goal_keys: Sequence[str],
    *,
    catalog: Mapping[str, Any] | None = None,
    absorbed: Sequence[str] | None = None,
    forage: bool = False,
    repo_root: Path = REPO_ROOT,
    live_fetch: bool = False,
) -> dict[str, Any]:
    """Probe ranked candidates until inferred provides cover the goal."""

    goals = tuple(str(item) for item in goal_keys if str(item).strip())
    payload = dict(catalog) if catalog is not None else load_growth_catalog()
    items = list(payload.get("items") or [])
    if not goals:
        return {
            "ok": False,
            "stage": "match",
            "error": "empty forage goal",
            "winner": None,
            "trend_winner": None,
            "probes": [],
            "ranked": [],
            "skipped": [],
        }
    ranking = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    result: dict[str, Any] = {
        "ok": bool(ranking["ok"]),
        "stage": "match",
        "error": ranking.get("error") or "",
        "winner": None,
        "trend_winner": ranking.get("winner"),
        "covering": None,
        "probes": [],
        "ranked": ranking.get("ranked") or [],
        "skipped": ranking.get("skipped") or [],
        "query": payload.get("query") or "",
        "goal_keys": list(goals),
    }
    if not ranking["ok"]:
        return result
    probes: list[dict[str, Any]] = []
    covering_entry: dict[str, Any] | None = None
    covering_probe: dict[str, Any] | None = None
    for entry in ranking.get("ranked") or []:
        probe = probe_candidate(entry, repo_root=repo_root, live_fetch=live_fetch)
        covers = _covers(probe, goals)
        probe["covers_goal"] = covers
        if probe.get("ok") and not covers:
            probe["skip_reason"] = "not_covering"
        probes.append(probe)
        if covers:
            covering_entry = dict(entry)
            covering_probe = probe
            break
    result["probes"] = probes
    result["live_fetch"] = bool(live_fetch)
    if covering_entry is None:
        result["ok"] = False
        result["error"] = "no forage match"
        return result
    result["ok"] = True
    result["error"] = ""
    result["winner"] = covering_entry
    result["covering"] = covering_probe
    if not forage:
        return result
    request = forage_request_for(covering_entry, repo_root=repo_root, live_fetch=live_fetch)
    request["bundle"] = True
    forage_result = forage_package(request, repo_root=repo_root)
    result["forage"] = {
        "ok": bool(forage_result.get("ok")),
        "slug": forage_result.get("slug"),
        "capability_id": forage_result.get("capability_id"),
        "runtime": forage_result.get("runtime"),
        "stage": forage_result.get("stage"),
        "error": forage_result.get("error"),
        "inferred_provides": list((forage_result.get("inference") or {}).get("provides") or [])
        if isinstance((forage_result.get("inference") or {}).get("provides"), list)
        else [str((forage_result.get("inference") or {}).get("provides") or "")]
        if (forage_result.get("inference") or {}).get("provides")
        else list((covering_probe or {}).get("inferred_provides") or []),
        "runtime_deps": list((forage_result.get("inference") or {}).get("runtime_deps") or [])
        or list((covering_probe or {}).get("runtime_deps") or []),
        "extra_paths": list((forage_result.get("inference") or {}).get("extra_paths") or [])
        or list((covering_probe or {}).get("extra_paths") or []),
    }
    result["ok"] = bool(forage_result.get("ok"))
    if not forage_result.get("ok"):
        result["stage"] = forage_result.get("stage") or "forage"
        result["error"] = str(forage_result.get("error") or "forage failed")
    return result


def _goal_task(record: Mapping[str, Any]) -> ApplicationTask:
    case = (record.get("cases") or [{}])[0]
    return ApplicationTask(
        id=f"forage-growth-{record.get('slug')}",
        description=f"Goal requiring foraged '{record.get('slug')}' output.",
        initial_state=dict(case.get("input") or {}),
        goal=tuple(str(key) for key in record.get("provides") or ()),
        oracle=dict(case.get("expect") or {}),
    )


def _honesty(slug: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    records = {str(item.get("slug")): item for item in load_persisted_records()}
    record = records.get(slug)
    if record is None:
        return {
            "ok": False,
            "unplannable_before": False,
            "grown_plan_solved": False,
            "ablation_unplannable": False,
            "error": f"no absorbed record: {slug}",
        }
    capability_id = str(record["capability_id"])
    task = _goal_task(record)
    ledger = load_ledger(default_ledger_path(repo_root))
    hidden = build_application_registry(
        ledger, hide=[capability_id], include_synthesized=True, include_absorbed=True
    )
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
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
    absorbed = sorted(HERMETIC_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(GOAL_KEY,))
    empty = rank_catalog([], absorbed=absorbed)
    no_goal = match_forage_goal((), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root)
    matched = match_forage_goal(
        (GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root
    )
    probes = list(matched.get("probes") or [])
    no_match_cover = any(_covers(row, (NO_MATCH_GOAL,)) for row in probes)
    decoy_probe = next((row for row in probes if row.get("slug") == DECOY_SLUG), {})
    skipped_reasons = {row["slug"]: row["skip_reason"] for row in trend.get("skipped") or []}
    return {
        "trend_winner_slug": (trend.get("winner") or {}).get("slug") or "",
        "trend_decoy_wins": (trend.get("winner") or {}).get("slug") == DECOY_SLUG,
        "lying_catalog_picks_decoy": (lying.get("winner") or {}).get("slug") == DECOY_SLUG,
        "match_is_forage_flip": (matched.get("winner") or {}).get("slug") == WINNER_SLUG,
        "decoy_probed_and_skipped": decoy_probe.get("skip_reason") == "not_covering"
        and GOAL_KEY not in set(decoy_probe.get("inferred_provides") or []),
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "empty_goal_refused": (not no_goal["ok"]) and no_goal.get("error") == "empty forage goal",
        "no_match_refused": bool(probes) and not no_match_cover,
        "empty_refused": (not empty["ok"]) and empty.get("error") == "empty forage catalog",
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


def run_forage_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Match the hermetic goal, forage the covering package, seal the evidence."""

    catalog = load_growth_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    forage_result: dict[str, Any] = {"ok": False}
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    if scenarios["match_is_forage_flip"] and forage:
        selected = match_forage_goal(
            (GOAL_KEY,),
            catalog=catalog,
            absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
            forage=True,
            repo_root=repo_root,
        )
        forage_result = dict(selected.get("forage") or {"ok": False})
        if forage_result.get("ok"):
            honesty = _honesty(WINNER_SLUG, repo_root)
    grade = {
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "match_is_forage_flip": bool(scenarios["match_is_forage_flip"]),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "empty_goal_refused": bool(scenarios["empty_goal_refused"]),
        "no_match_refused": bool(scenarios["no_match_refused"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool(forage_result.get("ok")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_forage_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "forage": forage_result,
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
        "winner": (scenarios["matched"] or {}).get("winner") or "",
        "grade": grade,
        "capability_id": forage_result.get("capability_id"),
    }


def verify_forage_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-match the hermetic catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_growth_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = {
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "match_is_forage_flip": bool(scenarios["match_is_forage_flip"]),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "empty_goal_refused": bool(scenarios["empty_goal_refused"]),
        "no_match_refused": bool(scenarios["no_match_refused"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool((report.get("forage") or {}).get("ok")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
    }
    expected_grade["ok"] = all(expected_grade.values())
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = ((report.get("scenarios") or {}).get("matched") or {}).get("winner") == WINNER_SLUG
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


def builtin_forage_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: matching falsifies catalog lies, then the sealed plane."""

    catalog = load_growth_catalog()
    scenarios = _scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-forage-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_forage_growth_plane(report_dir)
        verification = verify_forage_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["match_is_forage_flip"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_forage_growth_plane(report_dir)["ok"]

    verdicts = {
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "match_is_forage_flip": bool(scenarios["match_is_forage_flip"]),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "empty_goal_refused": bool(scenarios["empty_goal_refused"]),
        "no_match_refused": bool(scenarios["no_match_refused"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": (scenarios["matched"] or {}).get("winner") or "",
        "action": "forage_growth_plane",
        "used_skill_route_discovery": False,
    }


def forage_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_forage_growth import '
        "builtin_forage_growth_plane_proof; r=builtin_forage_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='forage_growth_plane' "
        "and r.get('trend_decoy_wins') and r.get('lying_catalog_picks_decoy') "
        "and r.get('match_is_forage_flip') and r.get('decoy_probed_and_skipped') "
        "and r.get('catalog_provides_ignored') and r.get('empty_goal_refused') "
        "and r.get('no_match_refused') and r.get('empty_refused') "
        "and r.get('absorbed_skipped') and r.get('nonviable_skipped') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_forage_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the forage-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.forage-growth-plane",
        name="Forage-growth matching plane",
        description=(
            "Goal-driven forage matching: an unsolved goal ranks a catalog "
            "without a human-named package and without trusting pre-declared "
            "provides, probes candidates through foraging inference, forages "
            "the first package whose inferred behavior covers the goal, and "
            "proves a previously unplannable goal becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_forage_growth:demo_forage_growth_plane",
        proof_command=forage_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_forage_growth.py",
            "src/blackhole_agent/capability_forage_targets.py",
            "src/blackhole_agent/capability_foraging.py",
            "tests/fixtures/forage_growth_catalog.json",
            "tests/fixtures/external_packages/forage-flip/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "An unsolved goal no longer needs a named package or a catalog "
            "provides annotation: ranked candidates are probed, a lying "
            "popular decoy is skipped, the covering package is foraged, and "
            "the goal that was honestly unplannable becomes solvable."
        ),
        tags=("foraging", "plane", "goal-driven", "matching"),
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


def demo_forage_growth_plane() -> dict[str, Any]:
    """Entry surface: run the hermetic plane and summarize the matched target."""

    result = run_forage_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "grade": result.get("grade"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forage-growth matching plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    match_parser = sub.add_parser("match", help="probe the catalog until a candidate covers the goal")
    match_parser.add_argument("--goal", action="append", required=True, help="goal key to cover")
    match_parser.add_argument("--forage", action="store_true", help="forage the matching winner")

    plane_parser = sub.add_parser("plane", help="run the sealed hermetic plane")
    plane_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    sub.add_parser("proof", help="run the registered forage-growth-plane proof")
    sub.add_parser("register", help="register and prove the plane in the live ledger")

    verify_parser = sub.add_parser("verify", help="verify a sealed forage-growth report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    args = parser.parse_args(argv)
    if args.command_name == "match":
        result = match_forage_goal(tuple(args.goal), forage=bool(args.forage))
    elif args.command_name == "plane":
        result = run_forage_growth_plane(forage=not args.no_forage)
    elif args.command_name == "proof":
        result = builtin_forage_growth_plane_proof()
    elif args.command_name == "register":
        result = register_forage_growth_plane_capability()
    else:
        result = verify_forage_growth_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
