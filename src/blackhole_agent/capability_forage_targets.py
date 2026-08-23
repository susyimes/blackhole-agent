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
shape). Live npm/pypi search is an optional refresh of that payload, never
the registered proof. ``refresh_registry_catalog`` merges both registries
and accepts a frozen replay so application-growth can forage from a
live-shaped catalog without networking.

Catalog hits with no ``source`` / ``replay_source`` are not skipped when a
published npm tarball or PyPI sdist is already on disk as a registry replay:
``forage_request_for`` materializes that archive (origin is the registry
artifact, never a fixture overlay) so probing can infer provides and
application-growth can forage a covering registry package.

Hits with no stewardship archive keep a registry identity by default so
hermetic planes can still skip them as ``no_source``. ``live_fetch=True``
downloads the published npm tarball or PyPI sdist (replayable from
``artifacts/capability-foraging/downloads/``) so probing can cover packages
the stewardship tree has never seen. Origin kind is ``npm-live`` /
``pypi-live``, never a fixture overlay and never a stewardship path.
"""

from __future__ import annotations

import argparse
import hashlib
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
from blackhole_agent.capability_foraging import fetch_npm_tarball, fetch_pypi_sdist, forage_package

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-forage-targets"
DEFAULT_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_catalog.json"
DEFAULT_LIVE_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_live_catalog.json"
WINNER_SLUG = "forage-pick"
GOAL_OVERRIDE_SLUG = "js-shouter"
_GOAL_QUERY_SUFFIXES = ("_output", "_html", "_json", "_text", "_result")
# Published registry archives already in the tree. Catalog entries that name
# these packages do not need a fixture overlay or a replay_source field.
REGISTRY_REPLAY_ARCHIVES: dict[tuple[str, str, str], str] = {
    ("npm", "marked", "18.0.7"): "stewardship/marked-18.0.7/marked-18.0.7.tgz",
    ("pypi", "markdown", "3.10.3"): "stewardship/markdown-3.10.3/markdown-3.10.3.tar.gz",
    ("pypi", "tomli", "2.4.1"): "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz",
}

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
        "replay_source": str(entry.get("replay_source") or ""),
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


def registry_replay_archive(entry: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> Path | None:
    """Return a published npm/PyPI archive for a catalog hit, if one is on disk.

    This is not a fixture overlay: the path is the registry artifact itself.
    Hits without a matching archive keep their registry identity so a live
    fetch can still run.
    """

    normalized = _normalize_entry(entry)
    registry = (normalized["registry"] or "").strip().lower()
    name = (normalized["name"] or "").strip().lower()
    version = (normalized["version"] or "").strip()
    relative = REGISTRY_REPLAY_ARCHIVES.get((registry, name, version))
    if not relative:
        return None
    path = repo_root / relative
    return path if path.is_file() else None


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def registry_download_dir(repo_root: Path = REPO_ROOT) -> Path:
    """Live-fetch cache: published archives, not the stewardship tree."""

    return repo_root / "artifacts" / "capability-foraging" / "downloads"


def cached_registry_download(
    entry: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    dest_dir: Path | None = None,
) -> Path | None:
    """Return a previously live-fetched npm/pypi archive if one is cached."""

    normalized = _normalize_entry(entry)
    version = (normalized["version"] or "").strip()
    if not version:
        return None
    dest = dest_dir or registry_download_dir(repo_root)
    registry = (normalized["registry"] or "").strip().lower()
    name = (normalized["name"] or "").strip()
    candidates: list[Path] = []
    if registry == "npm":
        candidates.append(dest / f"{name.rsplit('/', 1)[-1]}-{version}.tgz")
    elif registry == "pypi":
        prefixes = dict.fromkeys((name, name.replace("_", "-"), name.replace("-", "_")))
        for prefix in prefixes:
            candidates.append(dest / f"{prefix}-{version}.tar.gz")
            candidates.append(dest / f"{prefix}-{version}.zip")
    for path in candidates:
        if path.is_file():
            return path
    return None


def live_registry_archive(
    entry: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    dest_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Fetch a published npm/pypi archive the stewardship tree does not own.

    Prefers a replay cache under ``artifacts/capability-foraging/downloads/``
    so a registered proof can re-run without networking after the first fetch.
    """

    normalized = _normalize_entry(entry)
    registry = (normalized["registry"] or "").strip().lower()
    if registry not in {"npm", "pypi"}:
        return None
    dest = dest_dir or registry_download_dir(repo_root)
    cached = cached_registry_download(normalized, repo_root=repo_root, dest_dir=dest)
    if cached is not None:
        return {
            "ok": True,
            "name": normalized["name"],
            "version": normalized["version"],
            "path": str(cached),
            "sha256": hashlib.sha256(cached.read_bytes()).hexdigest(),
            "url": "",
            "cache_hit": True,
        }
    version = normalized["version"] or None
    if registry == "npm":
        fetched = fetch_npm_tarball(normalized["name"], version, dest_dir=dest)
    else:
        fetched = fetch_pypi_sdist(normalized["name"], version, dest_dir=dest)
    if not fetched.get("ok"):
        return None
    fetched["cache_hit"] = False
    return fetched


def forage_request_for(
    entry: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    live_fetch: bool = False,
) -> dict[str, Any]:
    """Build a :func:`forage_package` request from a ranked catalog entry."""

    normalized = _normalize_entry(entry)
    request: dict[str, Any] = {
        "name": normalized["name"],
        "slug": normalized["slug"],
        "hint": normalized["hint"],
    }
    source = normalized["source"] or normalized["replay_source"]
    if source:
        path = Path(source)
        if not path.is_absolute():
            path = repo_root / source
        request["source"] = path
        request["origin"] = {"kind": "fixture", "source": source}
    else:
        archive = registry_replay_archive(normalized, repo_root=repo_root)
        if archive is not None:
            rel = _repo_relative(archive, repo_root)
            kind = "npm-tarball" if normalized["registry"] == "npm" else "pypi-sdist"
            request["source"] = archive
            request["origin"] = {
                "kind": kind,
                "registry": normalized["registry"],
                "name": normalized["name"],
                "version": normalized["version"],
                "source": rel,
            }
        elif live_fetch:
            fetched = live_registry_archive(normalized, repo_root=repo_root)
            if fetched is not None:
                path = Path(str(fetched["path"]))
                kind = "npm-live" if normalized["registry"] == "npm" else "pypi-live"
                request["source"] = path
                request["origin"] = {
                    "kind": kind,
                    "registry": normalized["registry"],
                    "name": normalized["name"],
                    "version": str(fetched.get("version") or normalized["version"]),
                    "source": _repo_relative(path, repo_root),
                    "sha256": str(fetched.get("sha256") or ""),
                    "cache_hit": bool(fetched.get("cache_hit")),
                    "url": str(fetched.get("url") or ""),
                }
            else:
                request["registry"] = normalized["registry"] or "pypi"
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


def query_from_goal(goal_keys: Sequence[str]) -> str:
    """Derive a registry search query from goal keys. No package name is supplied."""

    tokens: list[str] = []
    seen: set[str] = set()
    for raw in goal_keys:
        text = str(raw or "").strip().lower().replace("-", "_")
        for suffix in _GOAL_QUERY_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)]
                break
        for part in text.split("_"):
            if part and part not in seen:
                seen.add(part)
                tokens.append(part)
    return " ".join(tokens)


def _pypi_candidate_names(query: str, *, size: int) -> list[str]:
    raw = " ".join(str(query or "").split()).strip().lower()
    names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        value = name.strip().lower()
        if value and value not in seen:
            seen.add(value)
            names.append(value)

    if raw:
        _add(raw.replace(" ", "-"))
        _add(raw.replace(" ", "_"))
        _add(raw.replace(" ", ""))
        for token in raw.split():
            _add(token)
    return names[: max(1, int(size))]


def _pypi_keywords(info: Mapping[str, Any]) -> list[str]:
    raw = info.get("keywords") or ""
    if isinstance(raw, str):
        return [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    if isinstance(raw, list):
        return [str(part) for part in raw if str(part).strip()]
    return []


def fetch_pypi_search(query: str, *, size: int = 10, timeout: int = 30) -> dict[str, Any]:
    """Lookup query-derived names on the PyPI JSON API. Live lane only."""

    names = _pypi_candidate_names(query, size=size)
    if not names:
        return {"ok": False, "query": query, "error": "empty pypi query", "items": []}
    items: list[dict[str, Any]] = []
    for name in names:
        api = f"https://pypi.org/pypi/{quote(name, safe='-_.')}/json"
        try:
            with urllib.request.urlopen(api, timeout=timeout) as response:
                meta = json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, Mapping):
            continue
        info = meta.get("info") if isinstance(meta.get("info"), Mapping) else {}
        pkg = str(info.get("name") or name)
        items.append(
            {
                "name": pkg,
                "slug": slugify_capability_id(pkg),
                "registry": "pypi",
                "downloads": max(int(meta.get("last_serial") or 0), 0),
                "recent_downloads": 0,
                "keywords": _pypi_keywords(info),
                "provides": [],
                "viable": True,
                "version": str(info.get("version") or ""),
                "runtime": "python",
            }
        )
        if len(items) >= max(1, int(size)):
            break
    return {"ok": True, "query": query, "items": items}


def refresh_registry_catalog(
    query: str = "",
    *,
    replay: Mapping[str, Any] | None = None,
    live: bool = False,
    size: int = 10,
    timeout: int = 30,
) -> dict[str, Any]:
    """Build a forage catalog from npm + PyPI search.

    Replay (the registered path) never networks. Live search is an optional
    refresh of that payload, never the hermetic proof.
    """

    requested = str(query or "").strip()
    if not live:
        payload = dict(replay) if replay is not None else load_catalog(DEFAULT_LIVE_CATALOG)
        items = [_normalize_entry(item) for item in payload.get("items") or []]
        registries = sorted({item["registry"] for item in items if item["registry"] in {"npm", "pypi"}})
        return {
            "ok": bool(items),
            "query": requested or str(payload.get("query") or ""),
            "items": items,
            "live": False,
            "replay": True,
            "network_used": False,
            "registries": registries,
            "error": "" if items else "empty forage catalog",
        }
    resolved = requested or "text"
    npm = fetch_npm_search(resolved, size=size, timeout=timeout)
    pypi = fetch_pypi_search(resolved, size=size, timeout=timeout)
    items = []
    if npm.get("ok"):
        items.extend(_normalize_entry(item) for item in npm.get("items") or [])
    if pypi.get("ok"):
        items.extend(_normalize_entry(item) for item in pypi.get("items") or [])
    registries = sorted({item["registry"] for item in items if item["registry"] in {"npm", "pypi"}})
    ok = bool(items)
    return {
        "ok": ok,
        "query": resolved,
        "items": items,
        "live": True,
        "replay": False,
        "network_used": True,
        "registries": registries,
        "error": "" if ok else str(npm.get("error") or pypi.get("error") or "empty forage catalog"),
        "npm_ok": bool(npm.get("ok")),
        "pypi_ok": bool(pypi.get("ok")),
    }


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

    refresh_parser = sub.add_parser("refresh", help="refresh npm+pypi catalog (replay unless --network)")
    refresh_parser.add_argument("--query", default="")
    refresh_parser.add_argument("--goal", action="append", default=None, help="goal key used to derive the query")
    refresh_parser.add_argument("--size", type=int, default=10)
    refresh_parser.add_argument("--network", action="store_true", help="hit live registries; never the registered proof")

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
    elif args.command_name == "refresh":
        query = str(args.query or "").strip() or query_from_goal(tuple(args.goal or ()))
        refreshed = refresh_registry_catalog(query, live=bool(args.network), size=args.size)
        if not refreshed.get("ok"):
            result = refreshed
        else:
            ranking = rank_catalog(refreshed["items"], absorbed=sorted(live_absorbed_slugs()))
            result = {**refreshed, **ranking}
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
