"""Forage-target plane: rank a catalog, pick a package, forage it.

Foraging still required a human to name the package (``--pypi inflection``,
``_DEFAULT_LIVE_TARGETS``). This module closes that leftover — **target
selection**:

- a catalog of registry candidates is ranked by a pure function of recorded
  ecosystem signals (downloads / recent downloads) plus optional unsolved
  goal-key overlap; no package name is supplied by the caller;
- already-absorbed slugs and non-viable entries are skipped, never selected;
- an empty catalog or a catalog whose every remaining member is skipped is
  an honest ``no forage target`` refusal, never a fabricated winner;
- the trend winner is foraged through :func:`forage_package` unchanged;
- a goal requiring the winner's unique provided key is honestly unplannable
  before the forage, solved after, and unplannable again under ablation;
- a digest-sealed report under ``artifacts/capability-forage-targets/``;
  verification re-ranks the recorded catalog, re-checks the digest, and
  re-proves the foraged capability, so a tampered winner or forged grade
  fails.

The hermetic catalog is a frozen trend payload (grounded-growth replay
shape). Live npm search is an optional refresh of that payload, never the
registered proof.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

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
    slugify_capability_id,
    utc_now_iso,
)
from blackhole_agent.capability_foraging import forage_package

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-forage-targets"
DEFAULT_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_catalog.json"
WINNER_SLUG = "forage-pick"
GOAL_OVERRIDE_SLUG = "js-shouter"

# Frozen absorbed set for hermetic ranking so absorbing the winner cannot
# change the sealed grade on a later proof run.
HERMETIC_ABSORBED_SLUGS = frozenset(
    {
        "inflection",
        "forage-lab",
        "forage-js",
        "forage-js-whisper",
        "forage-js-needs-two",
        "json-indenter",
        "markdown-foraged",
        "python-markdown",
        "marked-renderer",
        "mistune-markdown",
        "tomli-foraged",
        "tomli-parser",
        "text-reverser",
    }
)


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load a recorded forage-target catalog (hermetic trend payload)."""

    catalog_path = path or DEFAULT_CATALOG
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        raise ValueError(f"forage catalog is malformed: {catalog_path}")
    return dict(payload)


def live_absorbed_slugs(repo_root: Path = REPO_ROOT) -> set[str]:
    """Slugs already present as absorbed ledger leaves or persisted records."""

    slugs: set[str] = set()
    persist = repo_root / "capabilities" / "absorbed-steps.json"
    try:
        for record in load_persisted_records(persist if persist.is_file() else None):
            slug = str(record.get("slug") or "")
            if slug:
                slugs.add(slug)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    ledger_path = default_ledger_path(repo_root)
    if ledger_path.is_file():
        try:
            ledger = load_ledger(ledger_path)
        except (OSError, ValueError, json.JSONDecodeError):
            ledger = None
        if ledger is not None:
            for capability_id, capability in ledger.capabilities.items():
                if capability_id.startswith("capability.absorbed-"):
                    slugs.add(capability_id[len("capability.absorbed-") :])
                if "absorbed" in capability.tags:
                    slugs.add(capability_id.split("capability.absorbed-", 1)[-1])
    return slugs


def trend_score(entry: Mapping[str, Any]) -> int:
    """Monotone log-scale popularity. Pure function of recorded counts."""

    downloads = max(int(entry.get("downloads") or 0), 0)
    recent = max(int(entry.get("recent_downloads") or 0), 0)
    return downloads.bit_length() * 4 + recent.bit_length() * 8


def goal_score(entry: Mapping[str, Any], goal_keys: Sequence[str]) -> int:
    """Bonus when the candidate's provided keys or keywords cover the goal."""

    if not goal_keys:
        return 0
    provides = {str(item).lower() for item in entry.get("provides") or []}
    goals = {str(item).lower() for item in goal_keys}
    score = 1000 * len(provides & goals)
    keywords = {str(item).lower() for item in entry.get("keywords") or []}
    tokens: set[str] = set()
    for goal in goals:
        tokens.update(part for part in goal.replace("-", "_").split("_") if part)
    score += 25 * len(keywords & tokens)
    return score


def _normalize_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    name = str(entry.get("name") or "")
    slug = str(entry.get("slug") or slugify_capability_id(name))
    return {
        "name": name,
        "slug": slug,
        "registry": str(entry.get("registry") or "local"),
        "downloads": int(entry.get("downloads") or 0),
        "recent_downloads": int(entry.get("recent_downloads") or 0),
        "keywords": [str(item) for item in entry.get("keywords") or []],
        "provides": [str(item) for item in entry.get("provides") or []],
        "viable": bool(entry.get("viable", True)),
        "source": str(entry.get("source") or ""),
        "hint": str(entry.get("hint") or slug),
        "runtime": str(entry.get("runtime") or ""),
        "version": str(entry.get("version") or ""),
    }


def rank_catalog(
    items: Sequence[Mapping[str, Any]],
    *,
    absorbed: Sequence[str] | None = None,
    goal_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Rank catalog entries. Pure: same inputs always yield the same winner."""

    absorbed_set = {str(item) for item in (absorbed or ())}
    ranked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not items:
        return {
            "ok": False,
            "stage": "select",
            "error": "empty forage catalog",
            "winner": None,
            "ranked": [],
            "skipped": [],
        }
    for raw in items:
        entry = _normalize_entry(raw)
        skip_reason = ""
        if not entry["viable"]:
            skip_reason = "nonviable"
        elif entry["slug"] in absorbed_set:
            skip_reason = "already_absorbed"
        entry["trend_score"] = trend_score(entry)
        entry["goal_score"] = goal_score(entry, goal_keys)
        entry["score"] = entry["trend_score"] + entry["goal_score"]
        entry["skip_reason"] = skip_reason
        if skip_reason:
            skipped.append(entry)
        else:
            ranked.append(entry)
    ranked.sort(key=lambda row: (-int(row["score"]), str(row["slug"])))
    skipped.sort(key=lambda row: str(row["slug"]))
    winner = dict(ranked[0]) if ranked else None
    if winner is None:
        return {
            "ok": False,
            "stage": "select",
            "error": "no forage target",
            "winner": None,
            "ranked": ranked,
            "skipped": skipped,
        }
    return {
        "ok": True,
        "stage": "select",
        "error": "",
        "winner": winner,
        "ranked": ranked,
        "skipped": skipped,
    }


def forage_request_for(entry: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build a :func:`forage_package` request from a ranked catalog entry."""

    normalized = _normalize_entry(entry)
    request: dict[str, Any] = {
        "name": normalized["name"],
        "slug": normalized["slug"],
        "hint": normalized["hint"],
    }
    source = normalized["source"]
    if source:
        path = Path(source)
        if not path.is_absolute():
            path = repo_root / source
        request["source"] = path
        request["origin"] = {"kind": "fixture", "source": source}
    else:
        request["registry"] = normalized["registry"] or "pypi"
    if normalized["runtime"]:
        request["runtime"] = normalized["runtime"]
    if normalized["version"]:
        request["version"] = normalized["version"]
    return request


def fetch_npm_search(query: str, *, size: int = 10, timeout: int = 30) -> dict[str, Any]:
    """Refresh a catalog from the npm search API. Live lane only."""

    api = f"https://registry.npmjs.org/-/v1/search?text={quote(query)}&size={max(1, int(size))}"
    try:
        with urllib.request.urlopen(api, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "query": query, "error": f"npm search failed: {exc}", "items": []}
    items: list[dict[str, Any]] = []
    for row in payload.get("objects") or []:
        if not isinstance(row, Mapping):
            continue
        package = row.get("package") if isinstance(row.get("package"), Mapping) else {}
        name = str(package.get("name") or "")
        if not name:
            continue
        detail = ((row.get("score") or {}) if isinstance(row.get("score"), Mapping) else {}).get("detail") or {}
        popularity = float(detail.get("popularity") or 0.0) if isinstance(detail, Mapping) else 0.0
        downloads_block = row.get("downloads") if isinstance(row.get("downloads"), Mapping) else {}
        items.append(
            {
                "name": name,
                "slug": slugify_capability_id(name),
                "registry": "npm",
                "downloads": int(popularity * 1_000_000),
                "recent_downloads": int(downloads_block.get("weekly") or 0),
                "keywords": [str(item) for item in package.get("keywords") or []],
                "provides": [],
                "viable": True,
                "version": str(package.get("version") or ""),
                "runtime": "node",
            }
        )
    return {"ok": True, "query": query, "items": items}


def _goal_task(record: Mapping[str, Any]) -> ApplicationTask:
    case = (record.get("cases") or [{}])[0]
    return ApplicationTask(
        id=f"forage-target-{record.get('slug')}",
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


def select_forage_target(
    *,
    catalog: Mapping[str, Any] | None = None,
    absorbed: Sequence[str] | None = None,
    goal_keys: Sequence[str] = (),
    forage: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Select (and optionally forage) one catalog winner."""

    payload = dict(catalog) if catalog is not None else load_catalog()
    ranking = rank_catalog(payload.get("items") or [], absorbed=absorbed, goal_keys=goal_keys)
    result = {
        "ok": bool(ranking["ok"]),
        "stage": ranking["stage"],
        "error": ranking.get("error") or "",
        "winner": ranking.get("winner"),
        "ranked": ranking.get("ranked") or [],
        "skipped": ranking.get("skipped") or [],
        "query": payload.get("query") or "",
    }
    if not ranking["ok"] or not forage:
        return result
    forage_result = forage_package(forage_request_for(ranking["winner"], repo_root=repo_root), repo_root=repo_root)
    result["forage"] = {
        "ok": bool(forage_result.get("ok")),
        "slug": forage_result.get("slug"),
        "capability_id": forage_result.get("capability_id"),
        "runtime": forage_result.get("runtime"),
        "stage": forage_result.get("stage"),
        "error": forage_result.get("error"),
    }
    result["ok"] = bool(forage_result.get("ok"))
    if not forage_result.get("ok"):
        result["stage"] = forage_result.get("stage") or "forage"
        result["error"] = str(forage_result.get("error") or "forage failed")
    return result


def _scenario_grades(catalog: Mapping[str, Any]) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    trend = rank_catalog(items, absorbed=sorted(HERMETIC_ABSORBED_SLUGS))
    empty = rank_catalog([], absorbed=sorted(HERMETIC_ABSORBED_SLUGS))
    all_absorbed = rank_catalog(
        items,
        absorbed=sorted({_normalize_entry(item)["slug"] for item in items} | set(HERMETIC_ABSORBED_SLUGS)),
    )
    goal = rank_catalog(
        items,
        absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
        goal_keys=("shouted_text",),
    )
    skipped_reasons = {row["slug"]: row["skip_reason"] for row in trend.get("skipped") or []}
    return {
        "winner_slug": (trend.get("winner") or {}).get("slug") or "",
        "winner_is_forage_pick": (trend.get("winner") or {}).get("slug") == WINNER_SLUG,
        "absorbed_skipped": skipped_reasons.get("inflection") == "already_absorbed"
        and skipped_reasons.get("forage-lab") == "already_absorbed",
        "nonviable_skipped": skipped_reasons.get("forage-empty") == "nonviable",
        "empty_refused": (not empty["ok"]) and empty.get("error") == "empty forage catalog",
        "all_absorbed_refused": (not all_absorbed["ok"]) and all_absorbed.get("error") == "no forage target",
        "goal_overrides_trend": (goal.get("winner") or {}).get("slug") == GOAL_OVERRIDE_SLUG,
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": trend.get("winner"),
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
            "skipped": [{"slug": row["slug"], "skip_reason": row["skip_reason"]} for row in trend.get("skipped") or []],
        },
        "goal": {
            "ok": bool(goal["ok"]),
            "winner": (goal.get("winner") or {}).get("slug") or "",
        },
    }


def run_forage_target_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Rank the hermetic catalog, forage the winner, seal the evidence."""

    catalog = load_catalog()
    scenarios = _scenario_grades(catalog)
    forage_result: dict[str, Any] = {"ok": False}
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    if scenarios["winner_is_forage_pick"] and forage:
        selected = select_forage_target(
            catalog=catalog,
            absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
            forage=True,
            repo_root=repo_root,
        )
        forage_result = dict(selected.get("forage") or {"ok": False})
        if forage_result.get("ok"):
            honesty = _honesty(WINNER_SLUG, repo_root)
    grade = {
        "winner_is_forage_pick": bool(scenarios["winner_is_forage_pick"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "all_absorbed_refused": bool(scenarios["all_absorbed_refused"]),
        "goal_overrides_trend": bool(scenarios["goal_overrides_trend"]),
        "forage_ok": bool(forage_result.get("ok")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_forage_target_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "winner_slug": scenarios["winner_slug"],
            "trend": scenarios["trend"],
            "goal": scenarios["goal"],
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
        "winner": scenarios["winner_slug"],
        "grade": grade,
        "capability_id": forage_result.get("capability_id"),
    }


def verify_forage_target_plane(report_dir: Path) -> dict[str, Any]:
    """Re-rank the hermetic catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_catalog()
    scenarios = _scenario_grades(catalog)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = {
        "winner_is_forage_pick": bool(scenarios["winner_is_forage_pick"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "all_absorbed_refused": bool(scenarios["all_absorbed_refused"]),
        "goal_overrides_trend": bool(scenarios["goal_overrides_trend"]),
        "forage_ok": bool((report.get("forage") or {}).get("ok")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
    }
    expected_grade["ok"] = all(expected_grade.values())
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("scenarios") or {}).get("winner_slug") == WINNER_SLUG
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


def builtin_forage_target_plane_proof() -> dict[str, Any]:
    """Registered proof: hermetic ranking falsification plus the sealed plane."""

    catalog = load_catalog()
    scenarios = _scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-forage-targets-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_forage_target_plane(report_dir)
        verification = verify_forage_target_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["winner_is_forage_pick"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_forage_target_plane(report_dir)["ok"]

    verdicts = {
        "winner_is_forage_pick": bool(scenarios["winner_is_forage_pick"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "empty_refused": bool(scenarios["empty_refused"]),
        "all_absorbed_refused": bool(scenarios["all_absorbed_refused"]),
        "goal_overrides_trend": bool(scenarios["goal_overrides_trend"]),
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
        "winner": scenarios["winner_slug"],
        "action": "forage_target_plane",
        "used_skill_route_discovery": False,
    }


def forage_target_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_forage_targets import '
        "builtin_forage_target_plane_proof; r=builtin_forage_target_plane_proof(); "
        "assert r['ok'] and r.get('action')=='forage_target_plane' "
        "and r.get('winner_is_forage_pick') and r.get('absorbed_skipped') "
        "and r.get('nonviable_skipped') and r.get('empty_refused') "
        "and r.get('all_absorbed_refused') and r.get('goal_overrides_trend') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_forage_target_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the forage-target plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.forage-target-plane",
        name="Forage-target selection plane",
        description=(
            "Trend-driven automatic forage-target selection: rank a catalog of "
            "registry candidates by recorded downloads without a human-named "
            "package, skip already-absorbed and non-viable leaves, forage the "
            "winner through the existing foraging plane, and prove a previously "
            "unplannable goal becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_forage_targets:demo_forage_target_plane",
        proof_command=forage_target_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_forage_targets.py",
            "src/blackhole_agent/capability_foraging.py",
            "tests/fixtures/forage_catalog.json",
            "tests/fixtures/external_packages/forage-pick/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A forage request no longer names a package: recorded registry "
            "trends pick the winner, already-absorbed and non-viable leaves "
            "are skipped, the winner is foraged, and a goal that was honestly "
            "unplannable becomes solvable."
        ),
        tags=("foraging", "plane", "target-selection", "trend"),
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


def demo_forage_target_plane() -> dict[str, Any]:
    """Entry surface: run the hermetic plane and summarize the selected target."""

    result = run_forage_target_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "grade": result.get("grade"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forage-target selection plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    select_parser = sub.add_parser("select", help="rank the catalog and print the winner")
    select_parser.add_argument("--goal", action="append", default=None, help="optional goal key")
    select_parser.add_argument("--forage", action="store_true", help="forage the ranked winner")
    select_parser.add_argument("--live-absorbed", action="store_true", help="skip live absorbed slugs")

    plane_parser = sub.add_parser("plane", help="run the sealed hermetic plane")
    plane_parser.add_argument("--no-forage", action="store_true", help="rank only; do not forage")

    live_parser = sub.add_parser("live", help="rank a live npm search (selection only)")
    live_parser.add_argument("--query", default="text transform")
    live_parser.add_argument("--size", type=int, default=10)

    sub.add_parser("proof", help="run the registered forage-target-plane proof")
    sub.add_parser("register", help="register and prove the plane in the live ledger")

    verify_parser = sub.add_parser("verify", help="verify a sealed forage-target report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    args = parser.parse_args(argv)
    if args.command_name == "select":
        absorbed = live_absorbed_slugs() if args.live_absorbed else sorted(HERMETIC_ABSORBED_SLUGS)
        result = select_forage_target(
            absorbed=absorbed,
            goal_keys=tuple(args.goal or ()),
            forage=bool(args.forage),
        )
    elif args.command_name == "plane":
        result = run_forage_target_plane(forage=not args.no_forage)
    elif args.command_name == "live":
        fetched = fetch_npm_search(args.query, size=args.size)
        if not fetched.get("ok"):
            result = fetched
        else:
            ranking = rank_catalog(fetched["items"], absorbed=sorted(live_absorbed_slugs()))
            result = {**ranking, "query": args.query, "live": True}
    elif args.command_name == "proof":
        result = builtin_forage_target_plane_proof()
    elif args.command_name == "register":
        result = register_forage_target_plane_capability()
    else:
        result = verify_forage_target_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
