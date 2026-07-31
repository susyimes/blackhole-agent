"""Grounded growth scout: live GitHub trends distilled into repo improvement hypotheses.

The Unbound capability stack grew inward for five milestones (planes over
planes). This module re-anchors growth to external reality: it runs the live
GitHub trend intake, distills the discovered repositories into ranked,
surface-targeted improvement hypotheses for *this* repository, and records the
whole chain (query -> raw result -> hypotheses) as a digest-sealed artifact
under ``artifacts/grounded-growth/``.

Two invocation modes:

- live:   fetch from api.github.com, record the canonical payload so the run
          is replayable, then distill.
- replay: distill from a recorded payload only (hermetic; used by the
          registered capability proof and by tests).

Determinism contract: ``distill_hypotheses`` is a pure function of the
recorded payload. Replaying the same payload must reproduce the same
hypotheses and the same ``hypotheses_digest``; ``verify_grounded_scan``
recomputes every digest and re-distills from the recorded payload, so any
tamper or nondeterminism fails verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso
from blackhole_agent.github_growth import (
    GitHubEventsClient,
    GitHubTrendConfig,
    TrendingRepository,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/grounded-growth"
DEFAULT_FIXTURE = "tests/fixtures/grounded_scan_payload.json"

# Ordered keyword -> (target surface in this repository, pattern label).
# The first keyword that matches a repository decides its primary surface;
# every matched term is still recorded as evidence.
SURFACE_KEYWORDS: tuple[tuple[str, str, str], ...] = (
    ("eval", "src/blackhole_agent/harness_eval.py", "evaluation and benchmarking harness"),
    ("benchmark", "src/blackhole_agent/harness_eval.py", "evaluation and benchmarking harness"),
    ("memory", "src/blackhole_agent/local_memory.py", "durable agent memory"),
    ("rag", "src/blackhole_agent/local_memory.py", "durable agent memory"),
    ("mcp", "src/blackhole_agent/tool_routing.py", "tool exposure and routing"),
    ("function-calling", "src/blackhole_agent/tool_routing.py", "tool exposure and routing"),
    ("tool", "src/blackhole_agent/tool_routing.py", "tool exposure and routing"),
    ("sandbox", "src/blackhole_agent/kernels", "isolated kernel execution"),
    ("code-execution", "src/blackhole_agent/kernels", "isolated kernel execution"),
    ("swe", "src/blackhole_agent/kernels", "isolated kernel execution"),
    ("planner", "src/blackhole_agent/proposal_synthesis.py", "plan synthesis from signals"),
    ("reasoning", "src/blackhole_agent/proposal_synthesis.py", "plan synthesis from signals"),
    ("supply-chain", "src/blackhole_agent/ci_security.py", "CI and supply-chain security"),
    ("security", "src/blackhole_agent/ci_security.py", "CI and supply-chain security"),
    ("triage", "src/blackhole_agent/issue_triage.py", "issue and signal triage"),
    ("skill", "src/blackhole_agent/skill_routing.py", "skill routing"),
    ("agent", "src/blackhole_agent/unbound.py", "long-horizon agent runtime"),
)
FALLBACK_SURFACE = ("src/blackhole_agent/grounded_growth.py", "grounded growth scouting")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def repository_matched_terms(repo: TrendingRepository) -> list[str]:
    """Deterministically list the surface keywords a repository matches."""

    haystack = " ".join(
        [
            repo.full_name.lower(),
            repo.description.lower(),
            " ".join(topic.lower() for topic in repo.topics),
        ]
    )
    return [keyword for keyword, _, _ in SURFACE_KEYWORDS if keyword in haystack]


def repository_primary_surface(terms: Sequence[str]) -> tuple[str, str]:
    if not terms:
        return FALLBACK_SURFACE
    keyword = terms[0]
    for candidate, surface, pattern in SURFACE_KEYWORDS:
        if candidate == keyword:
            return surface, pattern
    return FALLBACK_SURFACE


def distill_hypotheses(
    repositories: Sequence[TrendingRepository],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Distill trending repositories into ranked, surface-targeted hypotheses.

    Pure function of the input. Repositories are grouped by their primary
    target surface; each group's score is the sum of log-scaled stars of its
    sources plus a bonus per distinct matched term. Ranking is by descending
    score with the surface path as deterministic tiebreak.
    """

    groups: dict[str, dict[str, Any]] = {}
    for repo in repositories:
        terms = repository_matched_terms(repo)
        surface, pattern = repository_primary_surface(terms)
        group = groups.setdefault(
            surface,
            {"surface": surface, "pattern": pattern, "sources": [], "terms": set()},
        )
        group["terms"].update(terms)
        group["sources"].append(repo)

    hypotheses: list[dict[str, Any]] = []
    for group in groups.values():
        sources = sorted(
            group["sources"],
            key=lambda repo: (-repo.stargazers_count, repo.full_name),
        )
        score = 0.0
        for repo in sources:
            # log1p without importing math keeps the function dependency-light;
            # use the integer bit length as a monotone log-scale proxy instead.
            score += 1.0 + max(repo.stargazers_count, 0).bit_length()
        score += 2.0 * len(group["terms"])
        top = sources[:3]
        terms = sorted(group["terms"])
        rationale = (
            f"{len(sources)} trending repositories "
            f"({', '.join(repo.full_name for repo in top)}) signal "
            f"'{group['pattern']}'; matched terms {terms}; "
            f"candidate surface {group['surface']}."
        )
        hypotheses.append(
            {
                "pattern": group["pattern"],
                "target_surface": group["surface"],
                "rationale": rationale,
                "score": round(score, 4),
                "matched_terms": terms,
                "sources": [
                    {
                        "full_name": repo.full_name,
                        "html_url": repo.html_url,
                        "stargazers_count": repo.stargazers_count,
                        "matched_terms": repository_matched_terms(repo),
                    }
                    for repo in sources[:5]
                ],
            }
        )

    hypotheses.sort(key=lambda item: (-item["score"], item["target_surface"]))
    for rank, item in enumerate(hypotheses[: max(limit, 0)], start=1):
        item["rank"] = rank
    return hypotheses[: max(limit, 0)]


def record_payload(
    result_repositories: Sequence[TrendingRepository],
    *,
    query: str,
    total_count: int,
) -> dict[str, Any]:
    """Canonical replayable form of one trend search result."""

    return {
        "query": query,
        "total_count": total_count,
        "items": [asdict(repo) for repo in result_repositories],
    }


def payload_to_repositories(payload: Mapping[str, Any]) -> list[TrendingRepository]:
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("recorded payload items must be a list")
    return [TrendingRepository(**{k: item.get(k) for k in TrendingRepository.__dataclass_fields__}) for item in items]


def write_scan_artifact(
    *,
    payload: Mapping[str, Any],
    hypotheses: list[dict[str, Any]],
    output_dir: Path,
    fetched_at: str,
    mode: str,
) -> dict[str, Any]:
    """Write the digest-sealed scan artifact and return its summary."""

    payload_digest = _digest(payload)
    hypotheses_digest = _digest(hypotheses)
    scan_digest = hashlib.sha256(f"{payload_digest}:{hypotheses_digest}".encode("utf-8")).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "payload.json", dict(payload))
    scan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "grounded_growth_scan",
        "mode": mode,
        "fetched_at": fetched_at,
        "query": payload.get("query", ""),
        "repository_count": len(payload.get("items") or []),
        "payload_digest": payload_digest,
        "hypotheses_digest": hypotheses_digest,
        "scan_digest": scan_digest,
        "hypotheses": hypotheses,
    }
    atomic_write_json(output_dir / "scan.json", scan)
    return {
        "ok": True,
        "output_dir": str(output_dir),
        "scan_digest": scan_digest,
        "payload_digest": payload_digest,
        "hypotheses_digest": hypotheses_digest,
        "hypothesis_count": len(hypotheses),
        "repository_count": scan["repository_count"],
        "top_hypothesis": hypotheses[0]["rationale"] if hypotheses else "",
    }


def run_live_scan(
    *,
    config: GitHubTrendConfig | None = None,
    output_dir: Path | None = None,
    session: Any = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Fetch live GitHub trends, record the payload, distill, and seal."""

    config = config or GitHubTrendConfig(query="topic:ai-agent", window_days=14, min_stars=50, limit=15)
    client = GitHubEventsClient(session=session)
    result = client.search_trending_repositories(config)
    payload = record_payload(result.repositories, query=result.query, total_count=result.total_count)
    hypotheses = distill_hypotheses(result.repositories)
    now = fetched_at or utc_now_iso()
    stamp = now.replace(":", "").replace("-", "")
    out = output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
    summary = write_scan_artifact(
        payload=payload,
        hypotheses=hypotheses,
        output_dir=out,
        fetched_at=now,
        mode="live",
    )
    summary["query"] = result.query
    return summary


def run_replay_scan(
    payload_path: Path,
    *,
    output_dir: Path,
    limit: int = 5,
) -> dict[str, Any]:
    """Hermetically distill from a recorded payload and seal a replay artifact."""

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    repositories = payload_to_repositories(payload)
    hypotheses = distill_hypotheses(repositories, limit=limit)
    summary = write_scan_artifact(
        payload=payload,
        hypotheses=hypotheses,
        output_dir=output_dir,
        fetched_at="replay",
        mode="replay",
    )
    summary["payload_path"] = str(payload_path)
    return summary


def verify_grounded_scan(scan_dir: Path) -> dict[str, Any]:
    """Recompute every digest and re-distill from the recorded payload."""

    scan_path = scan_dir / "scan.json"
    payload_path = scan_dir / "payload.json"
    if not scan_path.exists() or not payload_path.exists():
        return {"ok": False, "error": f"missing scan or payload in {scan_dir}"}
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    payload_digest = _digest(payload)
    hypotheses = distill_hypotheses(payload_to_repositories(payload))
    hypotheses_digest = _digest(hypotheses)
    scan_digest = hashlib.sha256(f"{payload_digest}:{hypotheses_digest}".encode("utf-8")).hexdigest()

    checks = {
        "payload_digest": payload_digest == scan.get("payload_digest"),
        "hypotheses_digest": hypotheses_digest == scan.get("hypotheses_digest"),
        "scan_digest": scan_digest == scan.get("scan_digest"),
        "redistilled_matches": hypotheses == scan.get("hypotheses"),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "scan_digest": scan_digest,
        "hypothesis_count": len(hypotheses),
    }


def builtin_grounded_scan_proof() -> dict[str, Any]:
    """Registered proof for ``capability.grounded-scan``.

    Replays the committed fixture payload, verifies the sealed artifact, and
    proves falsifiability: a tampered payload copy must fail verification.
    """

    import tempfile

    fixture = REPO_ROOT / DEFAULT_FIXTURE
    if not fixture.exists():
        return {"ok": False, "error": f"missing fixture {fixture}"}
    with tempfile.TemporaryDirectory(prefix="grounded-scan-proof-") as tmp:
        out = Path(tmp) / "scan"
        summary = run_replay_scan(fixture, output_dir=out)
        verified = verify_grounded_scan(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability: overwrite the recorded payload with a tampered copy
        # while keeping the original sealed scan; verification must fail.
        tampered = json.loads(fixture.read_text(encoding="utf-8"))
        items = list(tampered.get("items") or [])
        if items:
            first = dict(items[0])
            first["stargazers_count"] = int(first.get("stargazers_count") or 0) + 1
            items[0] = first
        tampered["items"] = items
        atomic_write_json(out / "payload.json", tampered)
        tamper_check = verify_grounded_scan(out)
        if tamper_check["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "tampered payload passed verification"}
        return {
            "ok": True,
            "hypothesis_count": summary["hypothesis_count"],
            "repository_count": summary["repository_count"],
            "scan_digest": summary["scan_digest"],
            "tamper_detected": not tamper_check["ok"],
            "top_hypothesis": summary["top_hypothesis"],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grounded growth scout")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="fetch live GitHub trends")
    mode.add_argument("--replay", type=Path, help="distill from a recorded payload JSON")
    mode.add_argument("--verify", type=Path, help="verify a sealed scan artifact directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--query", default="topic:ai-agent")
    parser.add_argument("--min-stars", type=int, default=50)
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args(argv)

    if args.live:
        config = GitHubTrendConfig(query=args.query, window_days=14, min_stars=args.min_stars, limit=args.limit)
        summary = run_live_scan(config=config, output_dir=args.output_dir)
    elif args.replay is not None:
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / "replay")
        summary = run_replay_scan(args.replay, output_dir=out)
    else:
        summary = verify_grounded_scan(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
