"""Upstream impact plane: close the post-publication outcome loop.

The publication plane (``upstream_publication``) opens a real pull request and
seals a receipt at actuation time. Nothing tracks whether those repairs land:
merge, close-without-merge, head divergence, or absorption into a released
version. The impact plane closes that gap.

For one sealed publication receipt the plane:

1. re-verifies the publication receipt seal (``receipt_unsealed`` refuses);
2. requires a successful publication verdict (``published`` /
   ``already_published`` / ``upstream_already_merged``) — dry-run and refusal
   receipts are not impact-assessable (``receipt_not_published``);
3. queries live PR state through an injected ``gh`` seam (default: real ``gh``
   CLI) and classifies the outcome:

   - ``impact_open`` — PR still open, head SHA matches the receipt
   - ``impact_open_diverged`` — PR open but head moved (new commits / force-push)
   - ``impact_merged`` — PR merged into the default branch
   - ``impact_closed_unmerged`` — PR closed without merge
   - ``impact_pr_missing`` — PR number no longer resolves upstream

4. optionally runs an injected ``absorption_checker`` to learn whether a
   released version (or HEAD) has absorbed the repair; when absorption is
   confirmed the outcome upgrades to ``impact_released`` (or records
   ``absorbed_at_head`` alongside the PR outcome);
5. seals an impact certificate under ``artifacts/upstream-impact/`` with
   sha256 digests of the publication receipt chain and the live PR snapshot;
   ``verify_impact_certificate`` re-checks digests and detects tampering.

Portfolio assessment walks published receipts under
``artifacts/upstream-publication/`` (or an explicit list), assesses each, and
seals a portfolio rollup with per-outcome counts and a chained digest. No
skill-route discovery is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent import upstream_publication as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-impact"
PUBLICATION_ARTIFACTS = REPO_ROOT / "artifacts" / "upstream-publication"

GH_TIMEOUT_SECONDS = 60

# Publication verdicts that represent a real outward PR (or a recorded merge).
PUBLISHED_VERDICTS = frozenset({
    "published",
    "already_published",
    "upstream_already_merged",
})

IMPACT_VERDICTS = frozenset({
    "impact_open",
    "impact_open_diverged",
    "impact_merged",
    "impact_closed_unmerged",
    "impact_pr_missing",
    "impact_released",
})

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class ImpactRefused(Exception):
    """A verdict-bearing refusal: impact must not be assessed."""

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


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _default_gh_runner(argv: Sequence[str], cwd: Path | None = None) -> str:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["CLICOLOR"] = "0"
    env["CLICOLOR_FORCE"] = "0"
    env["GH_FORCE_TTY"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    proc = subprocess.run(
        ["gh", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT_SECONDS,
        env=env,
    )
    if proc.returncode != 0:
        raise ImpactRefused(
            "gh_failed",
            f"gh {argv[0]} {argv[1] if len(argv) > 1 else ''}: {proc.stderr.strip()[:300]}",
        )
    return _strip_ansi(proc.stdout)


def _gh_json(gh: Callable[..., str], argv: Sequence[str]) -> Any:
    out = _strip_ansi(gh(list(argv)))
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError as exc:
        raise ImpactRefused(
            "gh_failed",
            f"gh returned non-JSON for {argv[:2]}: {exc}; raw={out[:120]!r}",
        )


def _repo_slug(repo_url: str) -> str:
    slug = repo_url.rstrip("/").removesuffix(".git")
    return slug.split("github.com/", 1)[-1]


# ---------------------------------------------------------------------------
# publication receipt intake


def load_publication_receipt(receipt_dir: Path) -> dict[str, Any]:
    """Load and re-verify a sealed publication receipt offline."""
    receipt_dir = Path(receipt_dir)
    receipt_path = durable_read_path(receipt_dir / "receipt.json")
    if not receipt_path.is_file():
        raise ImpactRefused("receipt_missing", f"no receipt.json under {receipt_dir}")
    checked = up.verify_publication_receipt(receipt_dir)
    if checked.get("mismatched"):
        raise ImpactRefused(
            "receipt_unsealed",
            f"publication payload digest mismatch: {', '.join(checked['mismatched'])}",
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("verdict") not in PUBLISHED_VERDICTS and not receipt.get("published"):
        raise ImpactRefused(
            "receipt_not_published",
            f"publication verdict {receipt.get('verdict')!r} is not impact-assessable",
        )
    # offline seal must hold even when verdict is a refusal-shaped edge case
    if checked.get("mismatched"):
        raise ImpactRefused("receipt_unsealed", "publication seal failed")
    receipt["_dir"] = str(receipt_dir)
    receipt["_receipt_sha256"] = _sha256_path(receipt_path)
    return receipt


# ---------------------------------------------------------------------------
# live PR query + outcome classification


def fetch_live_pr(
    upstream_repo: str,
    pr_number: int,
    *,
    gh: Callable[..., str],
) -> dict[str, Any] | None:
    """Return live PR fields, or None when the PR is missing."""
    slug = _repo_slug(upstream_repo)
    try:
        live = _gh_json(
            gh,
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                slug,
                "--json",
                "number,url,state,headRefOid,mergedAt,closedAt,title,baseRefName",
            ],
        )
    except ImpactRefused as exc:
        # gh exits non-zero when the PR is gone; treat as missing.
        if exc.verdict == "gh_failed" and (
            "Could not resolve" in exc.detail
            or "not found" in exc.detail.lower()
            or "HTTP 404" in exc.detail
        ):
            return None
        raise
    if not live or not live.get("number"):
        return None
    return live


def classify_impact(
    receipt: Mapping[str, Any],
    live: Mapping[str, Any] | None,
    *,
    absorption: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify post-publication outcome from live PR + optional absorption."""
    pr = receipt.get("pull_request") or {}
    recorded_sha = str(receipt.get("head_sha") or pr.get("headRefOid") or "")
    absorption = dict(absorption or {})

    if absorption.get("released"):
        return {
            "outcome": "impact_released",
            "detail": (
                f"repair absorbed in release "
                f"{absorption.get('release_version') or absorption.get('release') or 'unknown'}"
            ),
            "live_state": (live or {}).get("state"),
            "live_head": (live or {}).get("headRefOid"),
            "recorded_head": recorded_sha,
            "absorption": absorption,
        }

    if live is None:
        # Publication already recorded an upstream merge at actuation time.
        if receipt.get("verdict") == "upstream_already_merged":
            return {
                "outcome": "impact_merged",
                "detail": "publication receipt recorded upstream_already_merged; live PR unavailable",
                "live_state": None,
                "live_head": None,
                "recorded_head": recorded_sha,
                "absorption": absorption,
            }
        return {
            "outcome": "impact_pr_missing",
            "detail": f"PR #{pr.get('number')} no longer resolves on {receipt.get('upstream_repo')}",
            "live_state": None,
            "live_head": None,
            "recorded_head": recorded_sha,
            "absorption": absorption,
        }

    state = str(live.get("state") or "").upper()
    live_head = str(live.get("headRefOid") or "")
    merged_at = live.get("mergedAt")

    if state == "MERGED" or merged_at:
        return {
            "outcome": "impact_merged",
            "detail": f"PR #{live.get('number')} merged"
            + (f" at {merged_at}" if merged_at else ""),
            "live_state": state,
            "live_head": live_head,
            "recorded_head": recorded_sha,
            "absorption": absorption,
        }

    if state == "CLOSED":
        return {
            "outcome": "impact_closed_unmerged",
            "detail": f"PR #{live.get('number')} closed without merge",
            "live_state": state,
            "live_head": live_head,
            "recorded_head": recorded_sha,
            "absorption": absorption,
        }

    if state == "OPEN":
        if recorded_sha and live_head and live_head != recorded_sha:
            return {
                "outcome": "impact_open_diverged",
                "detail": (
                    f"PR #{live.get('number')} open but head moved "
                    f"({recorded_sha[:12]} -> {live_head[:12]})"
                ),
                "live_state": state,
                "live_head": live_head,
                "recorded_head": recorded_sha,
                "absorption": absorption,
            }
        return {
            "outcome": "impact_open",
            "detail": f"PR #{live.get('number')} still open; repair not yet landed",
            "live_state": state,
            "live_head": live_head,
            "recorded_head": recorded_sha,
            "absorption": absorption,
        }

    return {
        "outcome": "impact_pr_missing",
        "detail": f"unrecognized live PR state {state!r}",
        "live_state": state,
        "live_head": live_head,
        "recorded_head": recorded_sha,
        "absorption": absorption,
    }


# ---------------------------------------------------------------------------
# certificate sealing / verification


def _impact_digest_payload(certificate: Mapping[str, Any]) -> dict[str, Any]:
    """Fields that enter the impact digest (stable, no wall-clock)."""
    return {
        "schema_version": certificate.get("schema_version"),
        "publication_receipt_dir": certificate.get("publication_receipt_dir"),
        "publication_receipt_sha256": certificate.get("publication_receipt_sha256"),
        "name": certificate.get("name"),
        "version": certificate.get("version"),
        "defect_id": certificate.get("defect_id"),
        "upstream_repo": certificate.get("upstream_repo"),
        "branch": certificate.get("branch"),
        "pr_number": certificate.get("pr_number"),
        "pr_url": certificate.get("pr_url"),
        "outcome": certificate.get("outcome"),
        "live_state": certificate.get("live_state"),
        "live_head": certificate.get("live_head"),
        "recorded_head": certificate.get("recorded_head"),
        "absorption": certificate.get("absorption") or {},
        "publication_payload_sha256": certificate.get("publication_payload_sha256") or {},
    }


def _seal_impact_certificate(
    *,
    receipt: Mapping[str, Any],
    classification: Mapping[str, Any],
    live: Mapping[str, Any] | None,
    out_root: Path | None,
) -> dict[str, Any]:
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    name = str(receipt.get("name") or "unknown")
    version = str(receipt.get("version") or "0")
    defect_id = str(receipt.get("defect_id") or "defect")
    cert_dir = root / f"{name}-{version}" / defect_id / stamp
    cert_dir.mkdir(parents=True, exist_ok=True)

    pr = receipt.get("pull_request") or {}
    absorption = dict(classification.get("absorption") or {})

    certificate: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "publication_receipt_dir": str(receipt.get("_dir") or ""),
        "publication_receipt_sha256": receipt.get("_receipt_sha256"),
        "publication_payload_sha256": dict(receipt.get("payload_sha256") or {}),
        "publication_verdict": receipt.get("verdict"),
        "name": name,
        "version": version,
        "defect_id": defect_id,
        "upstream_repo": receipt.get("upstream_repo"),
        "branch": receipt.get("branch"),
        "pr_number": (live or pr).get("number") if (live or pr) else pr.get("number"),
        "pr_url": (live or pr).get("url") if (live or pr) else pr.get("url"),
        "outcome": classification["outcome"],
        "detail": classification.get("detail"),
        "live_state": classification.get("live_state"),
        "live_head": classification.get("live_head"),
        "recorded_head": classification.get("recorded_head"),
        "merged_at": (live or {}).get("mergedAt") if live else None,
        "closed_at": (live or {}).get("closedAt") if live else None,
        "absorption": absorption,
        "live_pr": dict(live) if live else None,
        "created_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    certificate["impact_digest"] = _sha256_json(_impact_digest_payload(certificate))
    atomic_write_json(cert_dir / "certificate.json", certificate)

    # Snapshot the live PR JSON for offline audit (not part of the digest).
    if live is not None:
        atomic_write_json(cert_dir / "live-pr.json", dict(live))

    return {
        "ok": True,
        "verdict": classification["outcome"],
        "outcome": classification["outcome"],
        "detail": classification.get("detail"),
        "certificate_dir": str(cert_dir),
        "impact_digest": certificate["impact_digest"],
        "name": name,
        "version": version,
        "defect_id": defect_id,
        "pr_number": certificate.get("pr_number"),
        "pr_url": certificate.get("pr_url"),
        "live_state": classification.get("live_state"),
        "absorption": absorption,
        "used_skill_route_discovery": certificate["used_skill_route_discovery"],
    }


def verify_impact_certificate(certificate_dir: Path) -> dict[str, Any]:
    """Re-check a sealed impact certificate: digests and publication chain."""
    certificate_dir = Path(certificate_dir)
    path = durable_read_path(certificate_dir / "certificate.json")
    if not path.is_file():
        return {"ok": False, "error": f"no certificate.json under {certificate_dir}", "mismatched": ["missing"]}
    certificate = json.loads(path.read_text(encoding="utf-8"))
    mismatched: list[str] = []

    expected = _sha256_json(_impact_digest_payload(certificate))
    if certificate.get("impact_digest") != expected:
        mismatched.append("impact_digest")

    # Re-hash the publication receipt file when still on disk.
    pub_dir = certificate.get("publication_receipt_dir")
    if pub_dir:
        pub_path = Path(str(pub_dir)) / "receipt.json"
        if pub_path.is_file():
            actual = _sha256_path(pub_path)
            if certificate.get("publication_receipt_sha256") and actual != certificate.get(
                "publication_receipt_sha256"
            ):
                mismatched.append("publication_receipt_sha256")
            # Also re-verify publication payload digests when present.
            pub_checked = up.verify_publication_receipt(Path(str(pub_dir)))
            if pub_checked.get("mismatched"):
                mismatched.append("publication_payload")
        # missing publication receipt is not a digest mismatch if path moved;
        # the sealed sha256 still binds the historical receipt.

    if certificate.get("outcome") not in IMPACT_VERDICTS:
        mismatched.append("outcome")

    return {
        "ok": not mismatched,
        "outcome": certificate.get("outcome"),
        "impact_digest": certificate.get("impact_digest"),
        "mismatched": mismatched,
        "used_skill_route_discovery": certificate.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# assess one / portfolio


def assess_publication_impact(
    receipt_dir: Path,
    *,
    gh: Callable[..., str] | None = None,
    absorption_checker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    out_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Assess post-publication impact for one sealed publication receipt.

    ``absorption_checker``, when provided, receives the loaded receipt and may
    return ``{"released": bool, "release_version": str, "absorbed_at_head": bool, ...}``.
    """
    receipt = load_publication_receipt(receipt_dir)
    runner = gh or _default_gh_runner

    pr = receipt.get("pull_request") or {}
    pr_number = pr.get("number")
    live: dict[str, Any] | None = None
    if pr_number and receipt.get("upstream_repo"):
        live = fetch_live_pr(str(receipt["upstream_repo"]), int(pr_number), gh=runner)
    elif receipt.get("verdict") != "upstream_already_merged":
        raise ImpactRefused(
            "pr_missing_on_receipt",
            "publication receipt has no pull_request.number to assess",
        )

    absorption: dict[str, Any] = {}
    if absorption_checker is not None:
        absorption = dict(absorption_checker(receipt) or {})

    classification = classify_impact(receipt, live, absorption=absorption)

    if dry_run:
        return {
            "ok": True,
            "verdict": classification["outcome"],
            "outcome": classification["outcome"],
            "detail": classification.get("detail"),
            "dry_run": True,
            "live_pr": live,
            "absorption": absorption,
            "name": receipt.get("name"),
            "version": receipt.get("version"),
            "defect_id": receipt.get("defect_id"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    sealed = _seal_impact_certificate(
        receipt=receipt,
        classification=classification,
        live=live,
        out_root=out_root,
    )
    verified = verify_impact_certificate(Path(sealed["certificate_dir"]))
    sealed["certificate_verified"] = bool(verified.get("ok"))
    sealed["ok"] = sealed["ok"] and sealed["certificate_verified"]
    return sealed


def discover_published_receipts(
    publication_root: Path | None = None,
) -> list[Path]:
    """Find the newest published receipt per (name, version, defect_id)."""
    root = Path(publication_root) if publication_root else PUBLICATION_ARTIFACTS
    if not root.is_dir():
        return []

    best: dict[tuple[str, str, str], tuple[str, Path]] = {}
    for receipt_path in root.rglob("receipt.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not receipt.get("published") and receipt.get("verdict") not in PUBLISHED_VERDICTS:
            continue
        if receipt.get("verdict") not in PUBLISHED_VERDICTS and not receipt.get("published"):
            continue
        # Prefer successful publication-shaped verdicts.
        if receipt.get("verdict") not in PUBLISHED_VERDICTS:
            continue
        key = (
            str(receipt.get("name") or ""),
            str(receipt.get("version") or ""),
            str(receipt.get("defect_id") or ""),
        )
        created = str(receipt.get("created_at") or receipt_path.parent.name)
        prev = best.get(key)
        if prev is None or created > prev[0]:
            best[key] = (created, receipt_path.parent)
    return [item[1] for item in sorted(best.values(), key=lambda x: x[0])]


def _portfolio_digest_payload(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": portfolio.get("schema_version"),
        "entries": [
            {
                "name": e.get("name"),
                "version": e.get("version"),
                "defect_id": e.get("defect_id"),
                "outcome": e.get("outcome"),
                "impact_digest": e.get("impact_digest"),
                "pr_number": e.get("pr_number"),
                "pr_url": e.get("pr_url"),
            }
            for e in (portfolio.get("entries") or [])
        ],
        "counts": portfolio.get("counts") or {},
        "assessed_count": portfolio.get("assessed_count"),
        "ok_count": portfolio.get("ok_count"),
    }


def assess_impact_portfolio(
    receipt_dirs: Sequence[Path] | None = None,
    *,
    publication_root: Path | None = None,
    gh: Callable[..., str] | None = None,
    absorption_checker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    out_root: Path | None = None,
) -> dict[str, Any]:
    """Assess a portfolio of published receipts and seal a rollup certificate."""
    dirs = list(receipt_dirs) if receipt_dirs is not None else discover_published_receipts(publication_root)
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    portfolio_dir = root / "portfolio" / stamp
    portfolio_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    failures: list[dict[str, Any]] = []

    for receipt_dir in dirs:
        try:
            result = assess_publication_impact(
                receipt_dir,
                gh=gh,
                absorption_checker=absorption_checker,
                out_root=root / "entries",
            )
        except ImpactRefused as exc:
            failures.append({
                "receipt_dir": str(receipt_dir),
                "verdict": exc.verdict,
                "detail": exc.detail,
            })
            counts[exc.verdict] = counts.get(exc.verdict, 0) + 1
            continue
        entries.append({
            "receipt_dir": str(receipt_dir),
            "certificate_dir": result.get("certificate_dir"),
            "name": result.get("name"),
            "version": result.get("version"),
            "defect_id": result.get("defect_id"),
            "outcome": result.get("outcome"),
            "impact_digest": result.get("impact_digest"),
            "pr_number": result.get("pr_number"),
            "pr_url": result.get("pr_url"),
            "live_state": result.get("live_state"),
            "ok": result.get("ok"),
        })
        outcome = str(result.get("outcome") or "unknown")
        counts[outcome] = counts.get(outcome, 0) + 1

    portfolio: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "assessed_count": len(entries),
        "ok_count": sum(1 for e in entries if e.get("ok")),
        "failure_count": len(failures),
        "counts": counts,
        "entries": entries,
        "failures": failures,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    portfolio["portfolio_digest"] = _sha256_json(_portfolio_digest_payload(portfolio))
    atomic_write_json(portfolio_dir / "portfolio.json", portfolio)

    return {
        "ok": len(failures) == 0 and len(entries) > 0 and all(e.get("ok") for e in entries),
        "verdict": "portfolio_assessed" if entries else "portfolio_empty",
        "portfolio_dir": str(portfolio_dir),
        "portfolio_digest": portfolio["portfolio_digest"],
        "assessed_count": portfolio["assessed_count"],
        "ok_count": portfolio["ok_count"],
        "failure_count": portfolio["failure_count"],
        "counts": counts,
        "entries": entries,
        "failures": failures,
        "used_skill_route_discovery": portfolio["used_skill_route_discovery"],
    }


def verify_impact_portfolio(portfolio_dir: Path) -> dict[str, Any]:
    """Re-check a sealed portfolio rollup and each entry certificate."""
    portfolio_dir = Path(portfolio_dir)
    path = durable_read_path(portfolio_dir / "portfolio.json")
    if not path.is_file():
        return {"ok": False, "error": "missing portfolio.json", "mismatched": ["missing"]}
    portfolio = json.loads(path.read_text(encoding="utf-8"))
    mismatched: list[str] = []
    expected = _sha256_json(_portfolio_digest_payload(portfolio))
    if portfolio.get("portfolio_digest") != expected:
        mismatched.append("portfolio_digest")

    entry_results = []
    for entry in portfolio.get("entries") or []:
        cert_dir = entry.get("certificate_dir")
        if not cert_dir:
            mismatched.append(f"entry:{entry.get('defect_id')}:missing_cert")
            continue
        checked = verify_impact_certificate(Path(str(cert_dir)))
        entry_results.append({
            "defect_id": entry.get("defect_id"),
            "ok": checked.get("ok"),
            "outcome": checked.get("outcome"),
        })
        if not checked.get("ok"):
            mismatched.append(f"entry:{entry.get('defect_id')}")

    return {
        "ok": not mismatched,
        "mismatched": mismatched,
        "entries": entry_results,
        "counts": portfolio.get("counts"),
        "used_skill_route_discovery": portfolio.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# hermetic proof fixtures


_PROOF_PUB_PAYLOAD = b"proof pr body for impact plane\n"
_PROOF_COMMIT = b"fix: proof impact\n\nGenerated-by: proof\n"


def _proof_publication_receipt(
    scratch: Path,
    *,
    verdict: str = "published",
    published: bool = True,
    pr_number: int = 42,
    pr_state: str = "OPEN",
    head_sha: str = "a" * 40,
    name: str = "impactprobe",
    version: str = "1.0.0",
    defect_id: str = "proof-defect",
    upstream_repo: str = "https://github.com/proof/impactprobe",
) -> Path:
    """Write a publication-plane-compatible sealed receipt for hermetic proofs."""
    receipt_dir = scratch / "pub" / f"{name}-{version}" / defect_id / "receipt-1"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / "pr-body.md").write_bytes(_PROOF_PUB_PAYLOAD)
    (receipt_dir / "commit-message.txt").write_bytes(_PROOF_COMMIT)
    digests = {
        "pr-body.md": _sha256_bytes(_PROOF_PUB_PAYLOAD),
        "commit-message.txt": _sha256_bytes(_PROOF_COMMIT),
    }
    receipt = {
        "schema_version": 1,
        "bundle_dir": str(scratch / "bundle"),
        "bundle_payload_sha256": {"contribution.patch": "b" * 64},
        "name": name,
        "version": version,
        "defect_id": defect_id,
        "upstream_repo": upstream_repo,
        "branch": f"blackhole/{defect_id}",
        "head_sha": head_sha,
        "verdict": verdict,
        "published": published,
        "pull_request": {
            "number": pr_number,
            "url": f"{upstream_repo}/pull/{pr_number}",
            "state": pr_state,
            "headRefOid": head_sha,
        },
        "payload_sha256": digests,
        "created_at": "2026-01-01T00:00:00Z",
        "used_skill_route_discovery": False,
    }
    atomic_write_json(receipt_dir / "receipt.json", receipt)
    return receipt_dir


class _FakeImpactGh:
    """Minimal gh seam: maps (repo_slug, pr_number) -> live PR payload or raises."""

    def __init__(self, live: Mapping[tuple[str, int], dict[str, Any] | None] | None = None):
        self.live = dict(live or {})
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], cwd: Path | None = None) -> str:
        args = list(argv)
        self.calls.append(args)
        # Expect: pr view <n> --repo <slug> --json ...
        if args[:2] == ["pr", "view"]:
            number = int(args[2])
            repo_idx = args.index("--repo") + 1
            slug = args[repo_idx]
            key = (slug, number)
            if key not in self.live:
                raise ImpactRefused("gh_failed", f"Could not resolve to a PullRequest: {slug}#{number}")
            payload = self.live[key]
            if payload is None:
                raise ImpactRefused("gh_failed", f"Could not resolve to a PullRequest: {slug}#{number}")
            return json.dumps(payload)
        raise ImpactRefused("gh_failed", f"unexpected gh argv: {args}")


def builtin_upstream_impact_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the impact plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="impact-proof-"))
    try:
        head = "c" * 40
        open_receipt = _proof_publication_receipt(
            scratch / "open",
            head_sha=head,
            pr_number=7,
            defect_id="open-defect",
        )
        merged_receipt = _proof_publication_receipt(
            scratch / "merged",
            head_sha=head,
            pr_number=8,
            defect_id="merged-defect",
            name="impactprobe",
            version="1.0.1",
        )
        closed_receipt = _proof_publication_receipt(
            scratch / "closed",
            head_sha=head,
            pr_number=9,
            defect_id="closed-defect",
            name="impactprobe",
            version="1.0.2",
        )
        diverged_receipt = _proof_publication_receipt(
            scratch / "diverged",
            head_sha=head,
            pr_number=10,
            defect_id="diverged-defect",
            name="impactprobe",
            version="1.0.3",
        )
        released_receipt = _proof_publication_receipt(
            scratch / "released",
            head_sha=head,
            pr_number=11,
            defect_id="released-defect",
            name="impactprobe",
            version="1.0.4",
        )
        missing_receipt = _proof_publication_receipt(
            scratch / "missing",
            head_sha=head,
            pr_number=12,
            defect_id="missing-defect",
            name="impactprobe",
            version="1.0.5",
        )

        slug = "proof/impactprobe"
        new_head = "d" * 40
        gh = _FakeImpactGh({
            (slug, 7): {
                "number": 7,
                "url": "https://github.com/proof/impactprobe/pull/7",
                "state": "OPEN",
                "headRefOid": head,
                "mergedAt": None,
                "closedAt": None,
                "title": "open",
                "baseRefName": "main",
            },
            (slug, 8): {
                "number": 8,
                "url": "https://github.com/proof/impactprobe/pull/8",
                "state": "MERGED",
                "headRefOid": head,
                "mergedAt": "2026-02-01T00:00:00Z",
                "closedAt": "2026-02-01T00:00:00Z",
                "title": "merged",
                "baseRefName": "main",
            },
            (slug, 9): {
                "number": 9,
                "url": "https://github.com/proof/impactprobe/pull/9",
                "state": "CLOSED",
                "headRefOid": head,
                "mergedAt": None,
                "closedAt": "2026-02-02T00:00:00Z",
                "title": "closed",
                "baseRefName": "main",
            },
            (slug, 10): {
                "number": 10,
                "url": "https://github.com/proof/impactprobe/pull/10",
                "state": "OPEN",
                "headRefOid": new_head,
                "mergedAt": None,
                "closedAt": None,
                "title": "diverged",
                "baseRefName": "main",
            },
            (slug, 11): {
                "number": 11,
                "url": "https://github.com/proof/impactprobe/pull/11",
                "state": "MERGED",
                "headRefOid": head,
                "mergedAt": "2026-03-01T00:00:00Z",
                "closedAt": "2026-03-01T00:00:00Z",
                "title": "released",
                "baseRefName": "main",
            },
            # 12 intentionally absent → pr_missing
        })

        out = scratch / "impact"

        open_r = assess_publication_impact(open_receipt, gh=gh, out_root=out)
        open_ok = open_r["ok"] and open_r["outcome"] == "impact_open"
        open_verified = verify_impact_certificate(Path(open_r["certificate_dir"]))

        merged_r = assess_publication_impact(merged_receipt, gh=gh, out_root=out)
        merged_ok = merged_r["ok"] and merged_r["outcome"] == "impact_merged"

        closed_r = assess_publication_impact(closed_receipt, gh=gh, out_root=out)
        closed_ok = closed_r["ok"] and closed_r["outcome"] == "impact_closed_unmerged"

        diverged_r = assess_publication_impact(diverged_receipt, gh=gh, out_root=out)
        diverged_ok = diverged_r["ok"] and diverged_r["outcome"] == "impact_open_diverged"

        def absorption_released(receipt: Mapping[str, Any]) -> dict[str, Any]:
            if receipt.get("defect_id") == "released-defect":
                return {"released": True, "release_version": "1.1.0", "absorbed_at_head": True}
            return {}

        released_r = assess_publication_impact(
            released_receipt, gh=gh, absorption_checker=absorption_released, out_root=out
        )
        released_ok = released_r["ok"] and released_r["outcome"] == "impact_released"

        missing_r = assess_publication_impact(missing_receipt, gh=gh, out_root=out)
        missing_ok = missing_r["ok"] and missing_r["outcome"] == "impact_pr_missing"

        # Tamper detection on open certificate.
        cert_path = Path(open_r["certificate_dir"]) / "certificate.json"
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
        cert["impact_digest"] = "0" * 64
        cert_path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
        tampered = verify_impact_certificate(Path(open_r["certificate_dir"]))
        tamper_detected = (not tampered.get("ok")) and "impact_digest" in (
            tampered.get("mismatched") or []
        )

        # Unsealed publication receipt refused.
        bad = _proof_publication_receipt(scratch / "bad", pr_number=99, defect_id="bad-defect")
        (bad / "pr-body.md").write_bytes(_PROOF_PUB_PAYLOAD + b"tamper")
        unsealed_refused = False
        try:
            assess_publication_impact(bad, gh=gh, out_root=out)
        except ImpactRefused as exc:
            unsealed_refused = exc.verdict == "receipt_unsealed"

        # Non-published receipt refused.
        dry = _proof_publication_receipt(
            scratch / "dry",
            verdict="dry_run_gates_passed",
            published=False,
            pr_number=100,
            defect_id="dry-defect",
        )
        not_published_refused = False
        try:
            assess_publication_impact(dry, gh=gh, out_root=out)
        except ImpactRefused as exc:
            not_published_refused = exc.verdict == "receipt_not_published"

        # Portfolio over the six assessable receipts (re-assess fresh open cert first).
        # Re-seal open after tamper for portfolio cleanliness.
        open_receipt2 = _proof_publication_receipt(
            scratch / "open2",
            head_sha=head,
            pr_number=7,
            defect_id="open-defect",
            version="2.0.0",
        )
        portfolio = assess_impact_portfolio(
            [
                open_receipt2,
                merged_receipt,
                closed_receipt,
                diverged_receipt,
                released_receipt,
                missing_receipt,
            ],
            gh=gh,
            absorption_checker=absorption_released,
            out_root=out / "portfolio-root",
        )
        portfolio_ok = (
            portfolio["ok"]
            and portfolio["assessed_count"] == 6
            and portfolio["counts"].get("impact_open") == 1
            and portfolio["counts"].get("impact_merged") == 1
            and portfolio["counts"].get("impact_closed_unmerged") == 1
            and portfolio["counts"].get("impact_open_diverged") == 1
            and portfolio["counts"].get("impact_released") == 1
            and portfolio["counts"].get("impact_pr_missing") == 1
        )
        portfolio_verified = verify_impact_portfolio(Path(portfolio["portfolio_dir"]))
        portfolio_seal_ok = bool(portfolio_verified.get("ok"))

        ok = all([
            open_ok,
            open_verified.get("ok"),
            merged_ok,
            closed_ok,
            diverged_ok,
            released_ok,
            missing_ok,
            tamper_detected,
            unsealed_refused,
            not_published_refused,
            portfolio_ok,
            portfolio_seal_ok,
            not open_r.get("used_skill_route_discovery"),
        ])
        return {
            "ok": ok,
            "open_classified": open_ok,
            "merged_classified": merged_ok,
            "closed_classified": closed_ok,
            "diverged_classified": diverged_ok,
            "released_classified": released_ok,
            "missing_classified": missing_ok,
            "certificate_verified": bool(open_verified.get("ok")),
            "tamper_detected": tamper_detected,
            "unsealed_refused": unsealed_refused,
            "not_published_refused": not_published_refused,
            "portfolio_assessed": portfolio_ok and portfolio_seal_ok,
            "portfolio_digest": portfolio.get("portfolio_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    assess_p = sub.add_parser("assess", help="Assess impact for one publication receipt")
    assess_p.add_argument("receipt_dir", type=Path)
    assess_p.add_argument("--out-root", type=Path, default=None)
    assess_p.add_argument("--dry-run", action="store_true")

    port_p = sub.add_parser("portfolio", help="Assess portfolio of published receipts")
    port_p.add_argument(
        "--publication-root",
        type=Path,
        default=None,
        help="root of upstream-publication artifacts (default: artifacts/upstream-publication)",
    )
    port_p.add_argument(
        "--receipt",
        action="append",
        dest="receipts",
        type=Path,
        default=None,
        help="explicit publication receipt dir (repeatable)",
    )
    port_p.add_argument("--out-root", type=Path, default=None)

    ver_p = sub.add_parser("verify", help="Verify an impact certificate")
    ver_p.add_argument("certificate_dir", type=Path)

    ver_port = sub.add_parser("verify-portfolio", help="Verify a portfolio rollup")
    ver_port.add_argument("portfolio_dir", type=Path)

    sub.add_parser("proof", help="Run hermetic builtin proof")
    sub.add_parser("discover", help="List newest published receipts")

    args = parser.parse_args(argv)

    if args.cmd == "assess":
        try:
            result = assess_publication_impact(
                args.receipt_dir,
                out_root=args.out_root,
                dry_run=args.dry_run,
            )
        except ImpactRefused as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "portfolio":
        try:
            result = assess_impact_portfolio(
                args.receipts,
                publication_root=args.publication_root,
                out_root=args.out_root,
            )
        except ImpactRefused as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify":
        result = verify_impact_certificate(args.certificate_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "verify-portfolio":
        result = verify_impact_portfolio(args.portfolio_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "discover":
        found = discover_published_receipts()
        print(json.dumps({"count": len(found), "receipts": [str(p) for p in found]}, indent=2))
        return 0

    if args.cmd == "proof":
        result = builtin_upstream_impact_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
