"""Upstream campaign plane: sealed end-to-end orchestration of the stewardship loop.

The upstream planes (discovery, admission, repair, contribution, publication,
impact) are independently invocable but require manual stage wiring. The
campaign plane closes that gap: one request drives a multi-stage campaign over
a stewarded target, with digest-chained receipts, stage short-circuits, and
optional outward publication plus post-publication outcome tracking.

For one stewardship target the plane can run any prefix/suffix of:

1. **discovery** — blind adversarial scan; seals a discovery report (findings
   + synthesized repros). Inject ``discovery_runner`` for hermetic proofs.
2. **admit** — promotes sealed discovery findings into stewardship defect
   entries (repro copy, optional patch bind, pending_patch when no patch).
   Requires a prior discovery stage or an explicit ``discovery_report_dir``.
3. **repair** — re-runs (or reuses a green) local repair campaign and records
   the report digests; a red repair aborts before any outward stage
   (``repair_failed``). Pending-patch defects are skipped by the repair plane.
4. **contribution** — builds a sealed contribution bundle for each requested
   defect (or every *patch-bound* defect on the manifest); already-fixed-at-HEAD
   defects are triaged non-submittable without aborting the campaign.
5. **publication** — for each submittable bundle, gates and optionally
   actuates publication (``publish=False`` default is dry-run only).
6. **impact** — optional post-publication stage: re-verifies sealed publication
   receipts from this campaign (or explicit ``impact_receipt_dirs``), classifies
   live PR outcomes via the impact plane, and chains impact certificate digests
   into the campaign receipt so full-loop stewardship ends in measured outcomes.

Seals a campaign receipt under ``artifacts/upstream-campaign/`` with sha256
digests of every stage artifact; ``verify_campaign_receipt`` re-checks the
chain and detects tampering.

The plane is orchestration, not a sixth independent verifier: each stage
delegates to the existing planes through injected seams so the builtin proof
is hermetic. No skill-route discovery is used.
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

from blackhole_agent import upstream_admission as ua
from blackhole_agent import upstream_contribution as uc
from blackhole_agent import upstream_discovery as udi
from blackhole_agent import upstream_impact as ui
from blackhole_agent import upstream_publication as up
from blackhole_agent import upstream_repair as ur
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-campaign"

DEFAULT_STAGES: tuple[str, ...] = ("repair", "contribution", "publication")
FULL_LOOP_STAGES: tuple[str, ...] = (
    "discovery",
    "admit",
    "repair",
    "contribution",
    "publication",
)
# Full stewardship loop including post-publication outcome closure.
OUTCOME_LOOP_STAGES: tuple[str, ...] = FULL_LOOP_STAGES + ("impact",)
VALID_STAGES = frozenset(OUTCOME_LOOP_STAGES)

# Publication verdicts whose sealed receipts the impact stage can assess.
_IMPACT_ASSESSABLE_PUBLICATION_VERDICTS = frozenset({
    "published",
    "already_published",
    "upstream_already_merged",
})


class CampaignRefused(Exception):
    """A verdict-bearing refusal: the campaign must not continue."""

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


def _load_manifest(target_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(target_dir) / "manifest.json")
    if not path.is_file():
        raise CampaignRefused("target_invalid", f"no manifest at {target_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_bound_defect_ids(manifest: Mapping[str, Any]) -> list[str]:
    """Defects that carry a patch (contribution/repair-ready), not pending admissions."""
    ids: list[str] = []
    for d in manifest.get("defects") or []:
        if not d.get("id"):
            continue
        if d.get("pending_patch") or not d.get("patch"):
            continue
        ids.append(str(d["id"]))
    return ids


def _defect_ids(
    manifest: Mapping[str, Any],
    requested: Sequence[str] | None,
    *,
    allow_empty: bool = False,
    patch_bound_only: bool = False,
) -> list[str]:
    if patch_bound_only:
        available = _patch_bound_defect_ids(manifest)
    else:
        available = [str(d["id"]) for d in manifest.get("defects", []) if d.get("id")]
    if not available:
        if allow_empty:
            return []
        raise CampaignRefused("no_defects", "manifest carries no defects to campaign")
    if not requested:
        return available
    unknown = [d for d in requested if d not in available]
    if unknown:
        raise CampaignRefused("defect_unknown", f"unknown defect ids: {unknown}")
    return list(requested)


# ---------------------------------------------------------------------------
# stages


def _stage_discovery(
    target_dir: Path,
    *,
    discovery_runner: Callable[[Path], dict[str, Any]] | None,
    artifact_root: Path | None,
) -> dict[str, Any]:
    """Run (or inject) a blind discovery scan; seal stage digests."""
    runner = discovery_runner or (
        lambda td: udi.run_discovery_scan(td, artifact_root=artifact_root)
    )
    result = runner(Path(target_dir))
    report_dir = result.get("report_dir")
    stage: dict[str, Any] = {
        "stage": "discovery",
        "verdict": "scanned" if result.get("ok") else "discovery_failed",
        "ok": bool(result.get("ok")),
        "report_dir": report_dir,
        "finding_count": result.get("finding_count"),
        "findings": result.get("findings"),
    }
    if report_dir:
        report_path = Path(report_dir) / "report.json"
        if report_path.is_file():
            stage["report_sha256"] = _sha256_path(report_path)
            seal = udi.verify_discovery_report(Path(report_dir))
            stage["seal_ok"] = bool(seal.get("ok"))
    if not result.get("ok"):
        stage["detail"] = result.get("error") or "discovery scan failed"
    return stage


def _stage_admit(
    target_dir: Path,
    report_dir: Path | None,
    *,
    admission_runner: Callable[..., dict[str, Any]] | None,
    patch_map: Mapping[str, str] | None,
    out_root: Path | None,
) -> dict[str, Any]:
    """Promote sealed discovery findings into the stewardship manifest."""
    if not report_dir:
        return {
            "stage": "admit",
            "verdict": "no_discovery_report",
            "ok": False,
            "detail": "admit requires a discovery report_dir",
        }
    runner = admission_runner or ua.admit_discovery_findings
    try:
        result = runner(
            Path(target_dir),
            Path(report_dir),
            patch_map=patch_map,
            out_root=out_root,
        )
    except ua.AdmissionRefused as exc:
        return {
            "stage": "admit",
            "verdict": exc.verdict,
            "ok": False,
            "detail": exc.detail,
        }
    except Exception as exc:  # noqa: BLE001 — stage isolation
        return {
            "stage": "admit",
            "verdict": "admission_error",
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}"[:400],
        }
    stage: dict[str, Any] = {
        "stage": "admit",
        "verdict": result.get("verdict"),
        "ok": bool(result.get("ok")),
        "receipt_dir": result.get("receipt_dir"),
        "admission_digest": result.get("admission_digest"),
        "admitted_count": result.get("admitted_count"),
        "pending_patch_ids": result.get("pending_patch_ids"),
        "admitted": result.get("admitted"),
    }
    receipt_dir = result.get("receipt_dir")
    if receipt_dir:
        receipt_json = Path(receipt_dir) / "receipt.json"
        if receipt_json.is_file():
            stage["receipt_sha256"] = _sha256_path(receipt_json)
            seal = ua.verify_admission_receipt(Path(receipt_dir))
            stage["seal_ok"] = bool(seal.get("ok"))
    return stage


def _target_repair_dir(target_dir: Path, artifact_dir: Path | None = None) -> Path:
    """Resolve the repair artifact directory for a stewardship target."""
    # Match upstream_repair._target_artifact_dir naming: name-version under ARTIFACT_DIR.
    manifest = _load_manifest(target_dir)
    root = Path(artifact_dir) if artifact_dir is not None else ur.ARTIFACT_DIR
    return root / f"{manifest['name']}-{manifest['version']}"


def _stage_repair(
    target_dir: Path,
    *,
    repair_runner: Callable[[Path], dict[str, Any]] | None,
    skip_if_green: bool,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    """Run or reuse the local repair campaign; refuse if red."""
    if skip_if_green:
        latest = ur.load_latest_report_dir(_target_repair_dir(target_dir, artifact_dir))
        if latest is not None:
            report_path = durable_read_path(latest / "report.json")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("ok") and report.get("repair_score") == 1.0:
                verified = ur.verify_repair_report(latest, target_dir)
                if verified.get("ok"):
                    return {
                        "stage": "repair",
                        "verdict": "reused_green",
                        "ok": True,
                        "report_dir": str(latest),
                        "report_digest": report.get("report_digest"),
                        "report_sha256": _sha256_path(report_path),
                        "reused": True,
                    }

    runner = repair_runner or (
        lambda td: ur.run_repair_campaign(td, artifact_dir=artifact_dir or ur.ARTIFACT_DIR)
    )
    report = runner(Path(target_dir))
    report_dir = report.get("report_dir")
    report_path = Path(report_dir) / "report.json" if report_dir else None
    stage = {
        "stage": "repair",
        "verdict": "repaired" if report.get("ok") else "repair_failed",
        "ok": bool(report.get("ok")),
        "report_dir": report_dir,
        "report_digest": report.get("report_digest"),
        "repair_score": report.get("repair_score"),
        "repaired_count": report.get("repaired_count"),
        "defect_count": report.get("defect_count"),
        "reused": False,
    }
    if report_path and report_path.is_file():
        stage["report_sha256"] = _sha256_path(report_path)
    if not report.get("ok"):
        stage["detail"] = report.get("error") or "repair campaign not green"
    return stage


def _stage_contribution(
    target_dir: Path,
    defect_ids: Sequence[str],
    *,
    contribution_builder: Callable[..., dict[str, Any]] | None,
    fetcher: Any,
    out_root: Path | None,
) -> dict[str, Any]:
    """Build sealed contribution bundles for each defect."""
    builder = contribution_builder or uc.build_contribution
    defects: list[dict[str, Any]] = []
    submittable_dirs: list[str] = []
    for defect_id in defect_ids:
        try:
            result = builder(
                Path(target_dir),
                defect_id,
                out_root=out_root,
                fetcher=fetcher,
            )
        except uc.ContributionRejected as exc:
            defects.append({
                "defect_id": defect_id,
                "ok": False,
                "submittable": False,
                "verdict": exc.verdict,
                "detail": exc.detail,
            })
            continue
        except Exception as exc:  # noqa: BLE001 — stage isolation: never crash the campaign
            defects.append({
                "defect_id": defect_id,
                "ok": False,
                "submittable": False,
                "verdict": "contribution_error",
                "detail": f"{type(exc).__name__}: {exc}"[:400],
            })
            continue
        bundle_dir = result.get("bundle_dir")
        entry: dict[str, Any] = {
            "defect_id": defect_id,
            "ok": bool(result.get("ok")),
            "submittable": bool(result.get("submittable")),
            "verdict": result.get("verdict"),
            "bundle_dir": bundle_dir,
        }
        if bundle_dir:
            bundle_json = Path(bundle_dir) / "bundle.json"
            if bundle_json.is_file():
                entry["bundle_sha256"] = _sha256_path(bundle_json)
                verified = uc.verify_contribution_bundle(Path(bundle_dir))
                entry["seal_ok"] = bool(verified.get("ok"))
            if result.get("submittable"):
                submittable_dirs.append(str(bundle_dir))
        defects.append(entry)

    any_ok = any(d.get("ok") for d in defects)
    any_submittable = any(d.get("submittable") for d in defects)
    all_triaged_fixed = bool(defects) and all(
        d.get("verdict") == "already_fixed_at_head" for d in defects
    )
    if all_triaged_fixed:
        verdict = "all_already_fixed"
    elif any_submittable:
        verdict = "submittable_ready"
    elif any_ok:
        verdict = "contribution_non_submittable"
    else:
        verdict = "contribution_failed"

    return {
        "stage": "contribution",
        "verdict": verdict,
        "ok": any_ok or all_triaged_fixed,
        "defects": defects,
        "submittable_bundle_dirs": submittable_dirs,
        "submittable_count": len(submittable_dirs),
    }


def _stage_publication(
    bundles: Sequence[str],
    *,
    publisher: Callable[..., dict[str, Any]] | None,
    publish: bool,
    gh: Callable[..., str] | None,
    verifier: Callable[..., dict[str, Any]] | None,
    manifest: Mapping[str, Any] | None,
    out_root: Path | None,
) -> dict[str, Any]:
    """Gate/actuate publication for each submittable bundle."""
    if not bundles:
        return {
            "stage": "publication",
            "verdict": "nothing_to_publish",
            "ok": True,
            "publications": [],
            "published_count": 0,
        }

    pub = publisher or up.publish_contribution
    publications: list[dict[str, Any]] = []
    for bundle_dir in bundles:
        try:
            result = pub(
                Path(bundle_dir),
                publish=publish,
                gh=gh,
                verifier=verifier,
                manifest=manifest,
                out_root=out_root,
            )
        except up.PublicationRefused as exc:
            publications.append({
                "bundle_dir": str(bundle_dir),
                "ok": False,
                "published": False,
                "verdict": exc.verdict,
                "detail": exc.detail,
            })
            continue
        entry: dict[str, Any] = {
            "bundle_dir": str(bundle_dir),
            "ok": bool(result.get("ok")),
            "published": bool(result.get("published")),
            "verdict": result.get("verdict"),
            "receipt_dir": result.get("receipt_dir"),
            "pull_request": result.get("pull_request"),
            "head_sha": result.get("head_sha"),
            "branch": result.get("branch"),
        }
        receipt_dir = result.get("receipt_dir")
        if receipt_dir:
            receipt_json = Path(receipt_dir) / "receipt.json"
            if receipt_json.is_file():
                entry["receipt_sha256"] = _sha256_path(receipt_json)
                verified = up.verify_publication_receipt(Path(receipt_dir), gh=gh if publish else None)
                entry["seal_ok"] = bool(verified.get("ok"))
        publications.append(entry)

    published_count = sum(1 for p in publications if p.get("published"))
    dry_count = sum(1 for p in publications if p.get("verdict") == "dry_run_gates_passed")
    if publish and published_count:
        verdict = "published"
    elif dry_count and not publish:
        verdict = "dry_run_gates_passed"
    elif all(p.get("verdict") in {"already_published", "upstream_already_merged", "upstream_closed_unmerged"} for p in publications):
        verdict = publications[0]["verdict"] if len(publications) == 1 else "publication_triaged"
    elif any(p.get("ok") for p in publications):
        verdict = "publication_partial"
    else:
        verdict = "publication_failed"

    return {
        "stage": "publication",
        "verdict": verdict,
        "ok": any(p.get("ok") for p in publications) or verdict == "nothing_to_publish",
        "publications": publications,
        "published_count": published_count,
        "publish_requested": publish,
    }


def _publication_receipt_dirs(publication_stage: Mapping[str, Any] | None) -> list[str]:
    """Receipt dirs from a publication stage that are impact-assessable."""
    dirs: list[str] = []
    for p in (publication_stage or {}).get("publications") or []:
        receipt_dir = p.get("receipt_dir")
        if not receipt_dir:
            continue
        verdict = str(p.get("verdict") or "")
        if p.get("published") or verdict in _IMPACT_ASSESSABLE_PUBLICATION_VERDICTS:
            dirs.append(str(receipt_dir))
    return dirs


def _stage_impact(
    receipt_dirs: Sequence[str],
    *,
    impact_assessor: Callable[..., dict[str, Any]] | None = None,
    gh: Callable[..., str] | None = None,
    absorption_checker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    out_root: Path | None = None,
) -> dict[str, Any]:
    """Assess post-publication impact for sealed publication receipts."""
    if not receipt_dirs:
        return {
            "stage": "impact",
            "verdict": "nothing_to_assess",
            "ok": True,
            "assessments": [],
            "assessed_count": 0,
            "outcomes": {},
        }

    assess = impact_assessor or ui.assess_publication_impact
    assessments: list[dict[str, Any]] = []
    for receipt_dir in receipt_dirs:
        try:
            result = assess(
                Path(receipt_dir),
                gh=gh,
                absorption_checker=absorption_checker,
                out_root=out_root,
            )
        except ui.ImpactRefused as exc:
            assessments.append({
                "receipt_dir": str(receipt_dir),
                "ok": False,
                "outcome": None,
                "verdict": exc.verdict,
                "detail": exc.detail,
            })
            continue
        entry: dict[str, Any] = {
            "receipt_dir": str(receipt_dir),
            "ok": bool(result.get("ok")),
            "outcome": result.get("outcome") or result.get("verdict"),
            "verdict": result.get("verdict") or result.get("outcome"),
            "detail": result.get("detail"),
            "certificate_dir": result.get("certificate_dir"),
            "impact_digest": result.get("impact_digest"),
            "pr_number": result.get("pr_number"),
            "pr_url": result.get("pr_url"),
            "live_state": result.get("live_state"),
            "name": result.get("name"),
            "version": result.get("version"),
            "defect_id": result.get("defect_id"),
            "absorption": result.get("absorption") or {},
        }
        cert_dir = result.get("certificate_dir")
        if cert_dir:
            cert_json = Path(str(cert_dir)) / "certificate.json"
            if cert_json.is_file():
                entry["certificate_sha256"] = _sha256_path(cert_json)
                verified = ui.verify_impact_certificate(Path(str(cert_dir)))
                entry["seal_ok"] = bool(verified.get("ok"))
        assessments.append(entry)

    outcomes: dict[str, int] = {}
    for a in assessments:
        key = str(a.get("outcome") or a.get("verdict") or "unknown")
        outcomes[key] = outcomes.get(key, 0) + 1

    assessed_ok = [a for a in assessments if a.get("ok") and a.get("outcome")]
    assessed_count = len(assessed_ok)
    if not assessments:
        verdict = "nothing_to_assess"
        ok = True
    elif assessed_count == 0:
        verdict = "impact_failed"
        ok = False
    elif assessed_count == len(assessments) and len(outcomes) == 1:
        # Single shared outcome across all assessed receipts.
        verdict = next(iter(outcomes))
        ok = True
    elif assessed_count == len(assessments):
        verdict = "impact_assessed"
        ok = True
    else:
        verdict = "impact_partial"
        ok = assessed_count > 0

    return {
        "stage": "impact",
        "verdict": verdict,
        "ok": ok,
        "assessments": assessments,
        "assessed_count": assessed_count,
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------------
# campaign orchestration


def run_campaign(
    target_dir: Path,
    *,
    defect_ids: Sequence[str] | None = None,
    stages: Sequence[str] = DEFAULT_STAGES,
    publish: bool = False,
    skip_repair_if_green: bool = True,
    repair_runner: Callable[[Path], dict[str, Any]] | None = None,
    contribution_builder: Callable[..., dict[str, Any]] | None = None,
    publisher: Callable[..., dict[str, Any]] | None = None,
    discovery_runner: Callable[[Path], dict[str, Any]] | None = None,
    admission_runner: Callable[..., dict[str, Any]] | None = None,
    impact_assessor: Callable[..., dict[str, Any]] | None = None,
    fetcher: Any = None,
    gh: Callable[..., str] | None = None,
    impact_gh: Callable[..., str] | None = None,
    absorption_checker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    verifier: Callable[..., dict[str, Any]] | None = None,
    repair_artifact_dir: Path | None = None,
    discovery_artifact_root: Path | None = None,
    discovery_report_dir: str | Path | None = None,
    admission_out_root: Path | None = None,
    admission_patch_map: Mapping[str, str] | None = None,
    contribution_out_root: Path | None = None,
    publication_out_root: Path | None = None,
    impact_out_root: Path | None = None,
    impact_receipt_dirs: Sequence[str | Path] | None = None,
    out_root: Path | None = None,
    bundle_dirs: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Run a multi-stage stewardship campaign and seal a campaign receipt.

    Parameters mirror the underlying planes so proofs can inject hermetic
    seams. ``publish=False`` (default) never performs outward GitHub mutation.

    ``bundle_dirs`` supplies pre-sealed contribution bundles for a publication
    stage that runs without (or after) contribution rebuild — used to publish
    an already-sealed submittable bundle through the campaign receipt chain.

    ``impact_receipt_dirs`` supplies explicit publication receipt directories for
    an impact stage (alone or in addition to receipts produced by a publication
    stage in this campaign). ``impact_gh`` defaults to ``gh`` when omitted.

    Full-loop stages (``discovery`` → ``admit`` → ``repair`` → ``contribution``
    → ``publication``) close the stewardship loop from a blind scan through
    optional outward publication. Append ``impact`` (or use
    ``OUTCOME_LOOP_STAGES``) to chain post-publication outcome certificates.
    Default stages remain the historical repair→contribution→publication
    suffix for backward compatibility.
    """
    target_dir = Path(target_dir)
    manifest = _load_manifest(target_dir)
    if not stages:
        raise CampaignRefused("stages_empty", "no stages requested")
    unknown = [s for s in stages if s not in VALID_STAGES]
    if unknown:
        raise CampaignRefused("stages_unknown", f"unknown stages: {unknown}")
    # Preserve caller order while dropping duplicates.
    stage_list = list(dict.fromkeys(s for s in stages if s in VALID_STAGES))

    needs_defects = any(s in stage_list for s in ("repair", "contribution", "publication"))
    # Discovery/admit may populate defects before outward stages run.
    # Impact-only campaigns may assess pre-sealed publication receipts.
    allow_empty_upfront = (
        ("discovery" in stage_list)
        or ("admit" in stage_list)
        or bool(bundle_dirs)
        or bool(impact_receipt_dirs)
        or (stage_list == ["impact"])
    )
    ids = _defect_ids(
        manifest,
        defect_ids,
        allow_empty=allow_empty_upfront or not needs_defects,
        patch_bound_only=False,
    )
    stage_results: dict[str, Any] = {}
    campaign_ok = True
    terminal_verdict = "campaign_complete"
    active_report_dir: Path | None = Path(discovery_report_dir) if discovery_report_dir else None

    # --- discovery ---
    if "discovery" in stage_list:
        discovery = _stage_discovery(
            target_dir,
            discovery_runner=discovery_runner,
            artifact_root=discovery_artifact_root,
        )
        stage_results["discovery"] = discovery
        if not discovery.get("ok"):
            campaign_ok = False
            terminal_verdict = "discovery_failed"
            return _seal_campaign(
                target_dir=target_dir,
                manifest=manifest,
                defect_ids=ids,
                stages=stage_list,
                stage_results=stage_results,
                publish=publish,
                ok=False,
                verdict=terminal_verdict,
                out_root=out_root,
            )
        if discovery.get("report_dir"):
            active_report_dir = Path(str(discovery["report_dir"]))

    # --- admit ---
    if "admit" in stage_list:
        admit = _stage_admit(
            target_dir,
            active_report_dir,
            admission_runner=admission_runner,
            patch_map=admission_patch_map,
            out_root=admission_out_root,
        )
        stage_results["admit"] = admit
        if not admit.get("ok"):
            campaign_ok = False
            terminal_verdict = "admit_failed"
            return _seal_campaign(
                target_dir=target_dir,
                manifest=_load_manifest(target_dir),
                defect_ids=ids,
                stages=stage_list,
                stage_results=stage_results,
                publish=publish,
                ok=False,
                verdict=terminal_verdict,
                out_root=out_root,
            )
        # Reload manifest + defect ids after admission mutates stewardship.
        manifest = _load_manifest(target_dir)
        ids = _defect_ids(
            manifest,
            defect_ids,
            allow_empty=True,
            patch_bound_only=False,
        )
        if admit.get("verdict") in {"admitted", "all_already_admitted", "nothing_to_admit"}:
            # Keep campaign_complete unless later stages override.
            if terminal_verdict == "campaign_complete" and not any(
                s in stage_list for s in ("repair", "contribution", "publication")
            ):
                terminal_verdict = str(admit.get("verdict") or "admitted")

    # --- repair ---
    if "repair" in stage_list:
        # Repair only acts on patch-bound defects; pending admissions are skipped.
        repair_ids = _defect_ids(manifest, defect_ids, allow_empty=True, patch_bound_only=True)
        if not repair_ids and not defect_ids:
            stage_results["repair"] = {
                "stage": "repair",
                "verdict": "no_patch_bound_defects",
                "ok": True,
                "reused": False,
                "detail": "no patch-bound defects; discovery admissions may still be pending_patch",
            }
            if terminal_verdict == "campaign_complete" and not any(
                s in stage_list for s in ("contribution", "publication")
            ):
                terminal_verdict = "no_patch_bound_defects"
        else:
            repair = _stage_repair(
                target_dir,
                repair_runner=repair_runner,
                skip_if_green=skip_repair_if_green,
                artifact_dir=repair_artifact_dir,
            )
            stage_results["repair"] = repair
            if not repair.get("ok"):
                campaign_ok = False
                terminal_verdict = "repair_failed"
                return _seal_campaign(
                    target_dir=target_dir,
                    manifest=manifest,
                    defect_ids=ids,
                    stages=stage_list,
                    stage_results=stage_results,
                    publish=publish,
                    ok=False,
                    verdict=terminal_verdict,
                    out_root=out_root,
                )

    # --- contribution ---
    submittable: list[str] = [str(p) for p in (bundle_dirs or [])]
    if "contribution" in stage_list:
        contrib_ids = _defect_ids(
            manifest,
            defect_ids,
            allow_empty=bool(submittable),
            patch_bound_only=True,
        )
        if not contrib_ids and not submittable:
            stage_results["contribution"] = {
                "stage": "contribution",
                "verdict": "no_patch_bound_defects",
                "ok": True,
                "defects": [],
                "submittable_bundle_dirs": [],
                "submittable_count": 0,
            }
            if terminal_verdict == "campaign_complete":
                terminal_verdict = "no_patch_bound_defects"
        else:
            contribution = _stage_contribution(
                target_dir,
                contrib_ids,
                contribution_builder=contribution_builder,
                fetcher=fetcher,
                out_root=contribution_out_root,
            )
            stage_results["contribution"] = contribution
            built = list(contribution.get("submittable_bundle_dirs") or [])
            submittable = built if built else submittable
            if contribution.get("verdict") == "contribution_failed" and not submittable:
                campaign_ok = False
                terminal_verdict = "contribution_failed"
                return _seal_campaign(
                    target_dir=target_dir,
                    manifest=manifest,
                    defect_ids=contrib_ids,
                    stages=stage_list,
                    stage_results=stage_results,
                    publish=publish,
                    ok=False,
                    verdict=terminal_verdict,
                    out_root=out_root,
                )
            if contribution.get("verdict") == "all_already_fixed" and not submittable:
                terminal_verdict = "all_already_fixed"
            ids = contrib_ids

    # --- publication ---
    if "publication" in stage_list:
        publication = _stage_publication(
            submittable,
            publisher=publisher,
            publish=publish,
            gh=gh,
            verifier=verifier,
            manifest=manifest,
            out_root=publication_out_root,
        )
        stage_results["publication"] = publication
        if not publication.get("ok"):
            campaign_ok = False
            terminal_verdict = "publication_failed"
        elif terminal_verdict in {"campaign_complete", "no_patch_bound_defects"}:
            if publication.get("verdict") == "nothing_to_publish":
                if stage_results.get("contribution", {}).get("verdict") == "all_already_fixed":
                    terminal_verdict = "all_already_fixed"
                elif stage_results.get("contribution", {}).get("verdict") == "no_patch_bound_defects":
                    terminal_verdict = "no_patch_bound_defects"
                else:
                    terminal_verdict = "campaign_complete_no_publication"
            else:
                terminal_verdict = str(publication.get("verdict") or "campaign_complete")

    # --- impact (optional post-publication outcome closure) ---
    if "impact" in stage_list:
        from_pub = _publication_receipt_dirs(stage_results.get("publication"))
        explicit = [str(p) for p in (impact_receipt_dirs or [])]
        # Explicit dirs first, then campaign-produced receipts (deduped, order-preserving).
        receipt_dirs = list(dict.fromkeys([*explicit, *from_pub]))
        impact = _stage_impact(
            receipt_dirs,
            impact_assessor=impact_assessor,
            gh=impact_gh if impact_gh is not None else gh,
            absorption_checker=absorption_checker,
            out_root=impact_out_root,
        )
        stage_results["impact"] = impact
        if not impact.get("ok"):
            campaign_ok = False
            terminal_verdict = "impact_failed"
        elif terminal_verdict in {
            "campaign_complete",
            "published",
            "already_published",
            "dry_run_gates_passed",
            "campaign_complete_no_publication",
            "no_patch_bound_defects",
            "all_already_fixed",
        }:
            # Surface the measured impact outcome when assessment produced one;
            # keep nothing_to_assess from masking a successful publication.
            if impact.get("verdict") == "nothing_to_assess":
                if terminal_verdict == "campaign_complete" and stage_list == ["impact"]:
                    terminal_verdict = "nothing_to_assess"
            else:
                terminal_verdict = str(impact.get("verdict") or "impact_assessed")

    return _seal_campaign(
        target_dir=target_dir,
        manifest=manifest,
        defect_ids=ids,
        stages=stage_list,
        stage_results=stage_results,
        publish=publish,
        ok=campaign_ok,
        verdict=terminal_verdict,
        out_root=out_root,
    )


def _seal_campaign(
    *,
    target_dir: Path,
    manifest: Mapping[str, Any],
    defect_ids: Sequence[str],
    stages: Sequence[str],
    stage_results: Mapping[str, Any],
    publish: bool,
    ok: bool,
    verdict: str,
    out_root: Path | None,
) -> dict[str, Any]:
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    name = f"{manifest.get('name')}-{manifest.get('version')}"
    campaign_dir = root / name / stamp
    campaign_dir.mkdir(parents=True, exist_ok=True)

    # Collect stage artifact digests for the seal chain.
    stage_digests: dict[str, str] = {}
    if "discovery" in stage_results:
        d = stage_results["discovery"]
        if d.get("report_sha256"):
            stage_digests["discovery.report"] = str(d["report_sha256"])
        stage_digests["discovery.verdict"] = _sha256_bytes(
            str(d.get("verdict") or "").encode("utf-8")
        )
    if "admit" in stage_results:
        a = stage_results["admit"]
        if a.get("receipt_sha256"):
            stage_digests["admit.receipt"] = str(a["receipt_sha256"])
        if a.get("admission_digest"):
            stage_digests["admit.admission_digest"] = str(a["admission_digest"])
        stage_digests["admit.verdict"] = _sha256_bytes(
            str(a.get("verdict") or "").encode("utf-8")
        )
    if "repair" in stage_results:
        r = stage_results["repair"]
        if r.get("report_sha256"):
            stage_digests["repair.report"] = str(r["report_sha256"])
        elif r.get("report_digest"):
            stage_digests["repair.report_digest"] = str(r["report_digest"])
    if "contribution" in stage_results:
        for i, d in enumerate(stage_results["contribution"].get("defects") or []):
            if d.get("bundle_sha256"):
                stage_digests[f"contribution.{d['defect_id']}.bundle"] = str(d["bundle_sha256"])
            stage_digests[f"contribution.{d['defect_id']}.verdict"] = _sha256_bytes(
                str(d.get("verdict") or "").encode("utf-8")
            )
    if "publication" in stage_results:
        for i, p in enumerate(stage_results["publication"].get("publications") or []):
            key = Path(str(p.get("bundle_dir") or i)).name
            if p.get("receipt_sha256"):
                stage_digests[f"publication.{key}.receipt"] = str(p["receipt_sha256"])
            stage_digests[f"publication.{key}.verdict"] = _sha256_bytes(
                str(p.get("verdict") or "").encode("utf-8")
            )
    if "impact" in stage_results:
        impact = stage_results["impact"]
        stage_digests["impact.verdict"] = _sha256_bytes(
            str(impact.get("verdict") or "").encode("utf-8")
        )
        for i, a in enumerate(impact.get("assessments") or []):
            key = str(a.get("defect_id") or Path(str(a.get("receipt_dir") or i)).name)
            if a.get("impact_digest"):
                stage_digests[f"impact.{key}.digest"] = str(a["impact_digest"])
            if a.get("certificate_sha256"):
                stage_digests[f"impact.{key}.certificate"] = str(a["certificate_sha256"])
            stage_digests[f"impact.{key}.outcome"] = _sha256_bytes(
                str(a.get("outcome") or a.get("verdict") or "").encode("utf-8")
            )

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "target": str(target_dir),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "upstream_repo": manifest.get("upstream_repo"),
        "ecosystem": manifest.get("ecosystem") or (
            "npm" if (manifest.get("driver") or {}).get("runtime") == "node" else "pypi"
        ),
        "defect_ids": list(defect_ids),
        "stages": list(stages),
        "publish_requested": publish,
        "stage_results": dict(stage_results),
        "stage_digests": stage_digests,
        "ok": ok,
        "verdict": verdict,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    chain = _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "name": receipt["name"],
        "version": receipt["version"],
        "defect_ids": receipt["defect_ids"],
        "stages": receipt["stages"],
        "stage_digests": stage_digests,
        "ok": ok,
        "verdict": verdict,
    })
    receipt["campaign_digest"] = chain
    atomic_write_json(campaign_dir / "receipt.json", receipt)
    # Human-readable stage summary (not sealed as content, only path recorded).
    summary_lines = [
        f"# Campaign {name}",
        f"verdict: {verdict}",
        f"ok: {ok}",
        f"defects: {', '.join(defect_ids)}",
        f"stages: {', '.join(stages)}",
        "",
    ]
    for stage_name in stages:
        sr = stage_results.get(stage_name) or {}
        summary_lines.append(f"## {stage_name}: {sr.get('verdict')} (ok={sr.get('ok')})")
    (campaign_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    return {
        "ok": ok,
        "verdict": verdict,
        "campaign_dir": str(campaign_dir),
        "campaign_digest": chain,
        "stage_results": dict(stage_results),
        "name": receipt["name"],
        "version": receipt["version"],
        "defect_ids": list(defect_ids),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def verify_campaign_receipt(campaign_dir: Path) -> dict[str, Any]:
    """Re-check a sealed campaign receipt: stage digests and chain must match."""
    campaign_dir = Path(campaign_dir)
    receipt_path = durable_read_path(campaign_dir / "receipt.json")
    if not receipt_path.is_file():
        return {"ok": False, "error": f"missing receipt: {receipt_path}"}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    mismatched: list[str] = []

    stage_results = receipt.get("stage_results") or {}
    stage_digests = dict(receipt.get("stage_digests") or {})

    # Recompute digests from live stage artifacts where present.
    discovery = stage_results.get("discovery") or {}
    if discovery.get("report_dir"):
        report_path = Path(discovery["report_dir"]) / "report.json"
        if report_path.is_file():
            actual = _sha256_path(report_path)
            expected = stage_digests.get("discovery.report")
            if expected and actual != expected:
                mismatched.append("discovery.report")
                problems.append("discovery report digest mismatch")
            seal = udi.verify_discovery_report(Path(discovery["report_dir"]))
            if discovery.get("ok") and not seal.get("ok"):
                problems.append(f"discovery seal broken: {seal.get('problems')}")

    admit = stage_results.get("admit") or {}
    if admit.get("receipt_dir"):
        receipt_json = Path(admit["receipt_dir"]) / "receipt.json"
        if receipt_json.is_file():
            actual = _sha256_path(receipt_json)
            expected = stage_digests.get("admit.receipt")
            if expected and actual != expected:
                mismatched.append("admit.receipt")
                problems.append("admission receipt digest mismatch")
            seal = ua.verify_admission_receipt(Path(admit["receipt_dir"]))
            if admit.get("ok") and not seal.get("ok"):
                problems.append(f"admission seal broken: {seal.get('problems')}")

    repair = stage_results.get("repair") or {}
    if repair.get("report_dir"):
        report_path = Path(repair["report_dir"]) / "report.json"
        if report_path.is_file():
            actual = _sha256_path(report_path)
            expected = stage_digests.get("repair.report")
            if expected and actual != expected:
                mismatched.append("repair.report")
                problems.append("repair report digest mismatch")

    for d in (stage_results.get("contribution") or {}).get("defects") or []:
        defect_id = d.get("defect_id")
        bundle_dir = d.get("bundle_dir")
        if defect_id and bundle_dir:
            bundle_json = Path(bundle_dir) / "bundle.json"
            if bundle_json.is_file():
                actual = _sha256_path(bundle_json)
                expected = stage_digests.get(f"contribution.{defect_id}.bundle")
                if expected and actual != expected:
                    mismatched.append(f"contribution.{defect_id}.bundle")
                    problems.append(f"contribution bundle digest mismatch for {defect_id}")
                # Also re-verify the contribution seal itself.
                seal = uc.verify_contribution_bundle(Path(bundle_dir))
                if d.get("submittable") and not seal.get("ok"):
                    problems.append(f"contribution seal broken for {defect_id}: {seal.get('mismatched')}")

    for p in (stage_results.get("publication") or {}).get("publications") or []:
        receipt_dir = p.get("receipt_dir")
        if not receipt_dir:
            continue
        pub_receipt = Path(receipt_dir) / "receipt.json"
        if not pub_receipt.is_file():
            continue
        actual = _sha256_path(pub_receipt)
        key = Path(str(p.get("bundle_dir") or "")).name
        expected = stage_digests.get(f"publication.{key}.receipt")
        if expected and actual != expected:
            mismatched.append(f"publication.{key}.receipt")
            problems.append(f"publication receipt digest mismatch for {key}")
        seal = up.verify_publication_receipt(Path(receipt_dir))
        if p.get("published") and not seal.get("ok"):
            problems.append(f"publication seal broken for {key}")

    for a in (stage_results.get("impact") or {}).get("assessments") or []:
        cert_dir = a.get("certificate_dir")
        if not cert_dir:
            continue
        cert_json = Path(str(cert_dir)) / "certificate.json"
        key = str(a.get("defect_id") or Path(str(a.get("receipt_dir") or "")).name)
        if cert_json.is_file():
            actual = _sha256_path(cert_json)
            expected = stage_digests.get(f"impact.{key}.certificate")
            if expected and actual != expected:
                mismatched.append(f"impact.{key}.certificate")
                problems.append(f"impact certificate digest mismatch for {key}")
            seal = ui.verify_impact_certificate(Path(str(cert_dir)))
            if a.get("ok") and not seal.get("ok"):
                problems.append(f"impact certificate seal broken for {key}")
            expected_digest = stage_digests.get(f"impact.{key}.digest")
            if expected_digest and a.get("impact_digest") and expected_digest != a.get("impact_digest"):
                mismatched.append(f"impact.{key}.digest")
                problems.append(f"impact digest mismatch for {key}")

    expected_chain = _sha256_json({
        "schema_version": receipt.get("schema_version", SCHEMA_VERSION),
        "name": receipt.get("name"),
        "version": receipt.get("version"),
        "defect_ids": receipt.get("defect_ids"),
        "stages": receipt.get("stages"),
        "stage_digests": stage_digests,
        "ok": receipt.get("ok"),
        "verdict": receipt.get("verdict"),
    })
    if expected_chain != receipt.get("campaign_digest"):
        mismatched.append("campaign_digest")
        problems.append("campaign chain digest mismatch")

    return {
        "ok": not problems and not mismatched,
        "problems": problems,
        "mismatched": mismatched,
        "campaign_digest": receipt.get("campaign_digest"),
        "verdict": receipt.get("verdict"),
        "name": receipt.get("name"),
        "version": receipt.get("version"),
    }


# ---------------------------------------------------------------------------
# hermetic proof


def builtin_upstream_campaign_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the campaign plane (no network).

    Builds a fabricated stewardship target, injects hermetic contribution
    and publication seams (reusing the contribution/publication proof
    fixtures), seals a campaign receipt across repair→contribution→publication,
    verifies the chain, detects tampering, proves already-fixed short-circuit,
    proves empty-defect refusal, and proves the optional impact stage chains
    post-publication outcome certificates into the campaign receipt.
    """
    scratch = Path(tempfile.mkdtemp(prefix="campaign-proof-"))
    try:
        # --- fabrications from contribution + publication planes ---
        target = uc._proof_target(scratch / "stewardship")
        repo_url = "https://github.com/proof/contribprobe"
        tag_url = uc.github_archive_url(repo_url, uc._PROOF_VERSION)
        head_url = uc.github_archive_url(repo_url, "HEAD")
        tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

        def fetcher_unfixed(url: str) -> bytes:
            if url == head_url:
                return uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
            return tag_archive

        def fetcher_fixed(url: str) -> bytes:
            if url == head_url:
                return uc._proof_archive(uc._PROOF_INIT_FIXED, top=f"{uc._PROOF_PKG}-HEAD")
            return tag_archive

        def repair_green(_td: Path) -> dict[str, Any]:
            report_dir = scratch / "repair-report"
            report_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "schema_version": 1,
                "ok": True,
                "repair_score": 1.0,
                "repaired_count": 1,
                "defect_count": 1,
                "report_digest": "a" * 64,
                "report_dir": str(report_dir),
            }
            atomic_write_json(report_dir / "report.json", report)
            return report

        # Publication remotes for the contribution-built patch won't match
        # pubprobe's scanner fixture. For the publication stage of the campaign
        # proof we inject a publisher that seals a real publication receipt via
        # the publication plane's own hermetic fixtures, keyed off the
        # contribution bundle path.
        upstream, fork = up._proof_remotes(scratch / "remotes", up._PROOF_SOURCE_V1)
        gh = up._FakeGh(fork)

        def publisher_hermetic(bundle_dir: Path, **kwargs: Any) -> dict[str, Any]:
            # Re-seal a publication-plane-compatible bundle and publish it.
            # The campaign plane cares that publisher is invoked with the
            # contribution bundle path and that the returned receipt is sealed.
            pub_bundle = up._proof_write_bundle(
                scratch / "pub-bundle" / Path(bundle_dir).name,
                patch=up._PROOF_PATCH,
                test_text=up._PROOF_TEST,
                repro_text=up._PROOF_REPRO,
            )
            return up.publish_contribution(
                pub_bundle,
                publish=kwargs.get("publish", False),
                gh=gh,
                verifier=up._proof_verifier,
                manifest={"contribution": {"tests_subdir": "tests"}},
                out_root=kwargs.get("out_root") or (scratch / "pub-receipts"),
            )

        # 1. Full campaign: repair → contribution → publication (publish=True).
        full = run_campaign(
            target,
            stages=("repair", "contribution", "publication"),
            publish=True,
            skip_repair_if_green=False,
            repair_runner=repair_green,
            fetcher=fetcher_unfixed,
            publisher=publisher_hermetic,
            contribution_out_root=scratch / "contrib",
            publication_out_root=scratch / "pub-receipts",
            out_root=scratch / "campaigns",
        )
        full_ok = (
            full["ok"]
            and full["verdict"] == "published"
            and full["stage_results"]["repair"]["ok"]
            and full["stage_results"]["contribution"]["submittable_count"] == 1
            and full["stage_results"]["publication"]["published_count"] == 1
        )
        campaign_dir = Path(full["campaign_dir"])
        verified = verify_campaign_receipt(campaign_dir)
        verify_ok = bool(verified.get("ok"))

        # 2. Tamper: flip campaign_digest / a stage digest and re-verify.
        receipt_path = campaign_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["campaign_digest"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_campaign_receipt(campaign_dir)
        tamper_detected = not tampered["ok"] and "campaign_digest" in (tampered.get("mismatched") or [])

        # 3. Already-fixed short-circuit: contribution triages, nothing published.
        fixed = run_campaign(
            target,
            stages=("contribution", "publication"),
            publish=True,
            fetcher=fetcher_fixed,
            publisher=publisher_hermetic,
            contribution_out_root=scratch / "contrib-fixed",
            publication_out_root=scratch / "pub-fixed",
            out_root=scratch / "campaigns-fixed",
        )
        fixed_ok = (
            fixed["ok"]
            and fixed["verdict"] == "all_already_fixed"
            and fixed["stage_results"]["contribution"]["verdict"] == "all_already_fixed"
            and fixed["stage_results"]["publication"]["verdict"] == "nothing_to_publish"
        )
        fixed_verified = verify_campaign_receipt(Path(fixed["campaign_dir"]))

        # 4. Repair failure aborts before contribution.
        def repair_red(_td: Path) -> dict[str, Any]:
            return {"ok": False, "error": "injected red", "repair_score": 0.0}

        contrib_calls = {"n": 0}

        def builder_count(*_a: Any, **_k: Any) -> dict[str, Any]:
            contrib_calls["n"] += 1
            raise AssertionError("contribution must not run after red repair")

        red = run_campaign(
            target,
            stages=("repair", "contribution", "publication"),
            publish=False,
            skip_repair_if_green=False,
            repair_runner=repair_red,
            contribution_builder=builder_count,
            out_root=scratch / "campaigns-red",
        )
        red_aborts = (
            not red["ok"]
            and red["verdict"] == "repair_failed"
            and contrib_calls["n"] == 0
            and "contribution" not in red["stage_results"]
        )

        # 5. Empty defects refuse.
        empty_target = scratch / "empty-target"
        empty_target.mkdir()
        (empty_target / "manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "name": "empty",
                "version": "0.0.1",
                "upstream_repo": "https://github.com/proof/empty",
                "defects": [],
            }),
            encoding="utf-8",
        )
        empty_refused = False
        try:
            run_campaign(empty_target, stages=("contribution",), out_root=scratch / "empty")
        except CampaignRefused as exc:
            empty_refused = exc.verdict == "no_defects"

        # 6. Dry-run publication gates without outward PR.
        gh2 = up._FakeGh(fork)
        dry = run_campaign(
            target,
            stages=("contribution", "publication"),
            publish=False,
            fetcher=fetcher_unfixed,
            publisher=lambda bundle_dir, **kwargs: up.publish_contribution(
                up._proof_write_bundle(
                    scratch / "dry-bundle" / Path(bundle_dir).name,
                    patch=up._PROOF_PATCH,
                    test_text=up._PROOF_TEST,
                    repro_text=up._PROOF_REPRO,
                ),
                publish=False,
                gh=gh2,
                verifier=up._proof_verifier,
                manifest={"contribution": {"tests_subdir": "tests"}},
                out_root=kwargs.get("out_root") or (scratch / "dry-receipts"),
            ),
            contribution_out_root=scratch / "contrib-dry",
            publication_out_root=scratch / "dry-receipts",
            out_root=scratch / "campaigns-dry",
        )
        dry_ok = (
            dry["ok"]
            and dry["verdict"] == "dry_run_gates_passed"
            and not gh2.prs
        )

        # 7. Full-loop: discovery → admit on an empty-defect staging target.
        # Inject a sealed discovery report; admission mutates the manifest;
        # repair short-circuits with no_patch_bound_defects (pending patch).
        loop_target = ua._proof_target(scratch / "full-loop")
        sealed_report = ua._proof_discovery_report(scratch / "loop-discovery")

        def discovery_inject(_td: Path) -> dict[str, Any]:
            return {
                "ok": True,
                "report_dir": str(sealed_report),
                "finding_count": 1,
                "findings": [{"generator": "nested_link", "flagged": True, "kind": "complexity"}],
            }

        loop = run_campaign(
            loop_target,
            stages=("discovery", "admit", "repair"),
            discovery_runner=discovery_inject,
            admission_out_root=scratch / "loop-admission",
            out_root=scratch / "campaigns-loop",
        )
        loop_manifest = json.loads((loop_target / "manifest.json").read_text(encoding="utf-8"))
        loop_ok = (
            loop["ok"]
            and loop["stage_results"]["discovery"]["ok"]
            and loop["stage_results"]["admit"]["ok"]
            and int(loop["stage_results"]["admit"].get("admitted_count") or 0) == 1
            and loop["stage_results"]["repair"]["verdict"] == "no_patch_bound_defects"
            and any(d.get("pending_patch") for d in (loop_manifest.get("defects") or []))
        )
        loop_verified = verify_campaign_receipt(Path(loop["campaign_dir"]))
        loop_seal_ok = bool(loop_verified.get("ok"))

        # 8. Impact stage: publication → impact chains outcome certificates.
        # Fresh remotes/gh produce a sealed published receipt; impact assessor
        # mirrors that PR into the impact FakeGh without mutating the receipt
        # (so publication digests in the campaign seal stay valid).
        impact_fork = up._proof_remotes(scratch / "impact-remotes", up._PROOF_SOURCE_V1)[1]
        impact_gh_pub = up._FakeGh(impact_fork)

        def publisher_for_impact(bundle_dir: Path, **kwargs: Any) -> dict[str, Any]:
            pub_bundle = up._proof_write_bundle(
                scratch / "impact-pub-bundle" / Path(bundle_dir).name,
                patch=up._PROOF_PATCH,
                test_text=up._PROOF_TEST,
                repro_text=up._PROOF_REPRO,
            )
            return up.publish_contribution(
                pub_bundle,
                publish=kwargs.get("publish", False),
                gh=impact_gh_pub,
                verifier=up._proof_verifier,
                manifest={"contribution": {"tests_subdir": "tests"}},
                out_root=kwargs.get("out_root") or (scratch / "impact-pub-receipts"),
            )

        def impact_assessor_hermetic(
            receipt_dir: Path,
            **kwargs: Any,
        ) -> dict[str, Any]:
            receipt = json.loads(
                (Path(receipt_dir) / "receipt.json").read_text(encoding="utf-8")
            )
            pr = receipt.get("pull_request") or {}
            number = int(pr.get("number") or 0)
            head = str(receipt.get("head_sha") or pr.get("headRefOid") or "")
            slug = "proof/pubprobe"
            impact_fake = ui._FakeImpactGh({
                (slug, number): {
                    "number": number,
                    "url": pr.get("url") or f"https://github.com/{slug}/pull/{number}",
                    "state": "OPEN",
                    "headRefOid": head,
                    "mergedAt": None,
                    "closedAt": None,
                    "title": "campaign impact proof",
                    "baseRefName": "main",
                }
            })
            return ui.assess_publication_impact(
                receipt_dir,
                gh=impact_fake,
                out_root=kwargs.get("out_root") or (scratch / "impact-certs"),
            )

        with_impact = run_campaign(
            target,
            stages=("contribution", "publication", "impact"),
            publish=True,
            fetcher=fetcher_unfixed,
            publisher=publisher_for_impact,
            impact_assessor=impact_assessor_hermetic,
            contribution_out_root=scratch / "contrib-impact",
            publication_out_root=scratch / "impact-pub-receipts",
            impact_out_root=scratch / "impact-certs",
            out_root=scratch / "campaigns-impact",
        )
        impact_stage = with_impact.get("stage_results", {}).get("impact") or {}
        impact_ok = (
            with_impact["ok"]
            and with_impact["verdict"] == "impact_open"
            and impact_stage.get("ok")
            and impact_stage.get("assessed_count") == 1
            and impact_stage.get("outcomes", {}).get("impact_open") == 1
            and (impact_stage.get("assessments") or [{}])[0].get("seal_ok")
        )
        impact_verified = verify_campaign_receipt(Path(with_impact["campaign_dir"]))
        impact_seal_ok = bool(impact_verified.get("ok"))
        # Impact digests must appear in the campaign seal chain.
        impact_receipt = json.loads(
            (Path(with_impact["campaign_dir"]) / "receipt.json").read_text(encoding="utf-8")
        )
        impact_digests_chained = any(
            k.startswith("impact.") and k.endswith(".digest")
            for k in (impact_receipt.get("stage_digests") or {})
        )

        # 9. Impact with nothing to assess (dry-run publication only).
        nothing = run_campaign(
            target,
            stages=("contribution", "publication", "impact"),
            publish=False,
            fetcher=fetcher_unfixed,
            publisher=lambda bundle_dir, **kwargs: up.publish_contribution(
                up._proof_write_bundle(
                    scratch / "nothing-bundle" / Path(bundle_dir).name,
                    patch=up._PROOF_PATCH,
                    test_text=up._PROOF_TEST,
                    repro_text=up._PROOF_REPRO,
                ),
                publish=False,
                gh=up._FakeGh(impact_fork),
                verifier=up._proof_verifier,
                manifest={"contribution": {"tests_subdir": "tests"}},
                out_root=kwargs.get("out_root") or (scratch / "nothing-pub"),
            ),
            contribution_out_root=scratch / "contrib-nothing",
            publication_out_root=scratch / "nothing-pub",
            out_root=scratch / "campaigns-nothing",
        )
        nothing_ok = (
            nothing["ok"]
            and nothing["stage_results"]["impact"]["verdict"] == "nothing_to_assess"
            and nothing["verdict"] == "dry_run_gates_passed"
        )

        ok = all([
            full_ok, verify_ok, tamper_detected, fixed_ok, fixed_verified.get("ok"),
            red_aborts, empty_refused, dry_ok, loop_ok, loop_seal_ok,
            impact_ok, impact_seal_ok, impact_digests_chained, nothing_ok,
        ])
        return {
            "ok": ok,
            "campaign_published": full_ok,
            "receipt_verified": verify_ok,
            "tamper_detected": tamper_detected,
            "already_fixed_short_circuit": fixed_ok,
            "repair_failure_aborts": red_aborts,
            "empty_defects_refused": empty_refused,
            "dry_run_gated": dry_ok,
            "full_loop_discovery_admit": loop_ok and loop_seal_ok,
            "impact_stage_chained": impact_ok and impact_seal_ok and impact_digests_chained,
            "impact_nothing_to_assess": nothing_ok,
            "campaign_digest": full.get("campaign_digest"),
            "impact_campaign_digest": with_impact.get("campaign_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", help="stewardship target directory")
    parser.add_argument("--defect", action="append", dest="defects", help="defect id (repeatable)")
    parser.add_argument(
        "--stages",
        default="repair,contribution,publication",
        help=(
            "comma-separated stages "
            "(discovery,admit,repair,contribution,publication,impact; "
            "default: repair,contribution,publication)"
        ),
    )
    parser.add_argument(
        "--full-loop",
        action="store_true",
        help="shorthand for stages=discovery,admit,repair,contribution,publication",
    )
    parser.add_argument(
        "--outcome-loop",
        action="store_true",
        help=(
            "shorthand for stages=discovery,admit,repair,contribution,publication,impact "
            "(full loop plus post-publication outcome closure)"
        ),
    )
    parser.add_argument(
        "--discovery-report",
        help="pre-sealed discovery report dir (skips live scan when used with admit)",
    )
    parser.add_argument(
        "--impact-receipt",
        action="append",
        dest="impact_receipts",
        default=None,
        help="publication receipt dir for impact stage (repeatable)",
    )
    parser.add_argument("--publish", action="store_true", help="perform outward publication")
    parser.add_argument("--force-repair", action="store_true", help="re-run repair even if green")
    parser.add_argument("--verify-receipt", help="verify a sealed campaign receipt")
    parser.add_argument("--proof", action="store_true", help="run the hermetic builtin proof")
    parser.add_argument("--json", action="store_true", help="print result as JSON")
    args = parser.parse_args(argv)

    if args.proof:
        result = builtin_upstream_campaign_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    if args.verify_receipt:
        result = verify_campaign_receipt(Path(args.verify_receipt))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    if not args.target:
        parser.error("--target is required unless --proof or --verify-receipt")

    if args.outcome_loop:
        stages = OUTCOME_LOOP_STAGES
    elif args.full_loop:
        stages = FULL_LOOP_STAGES
    else:
        stages = tuple(s.strip() for s in args.stages.split(",") if s.strip())
    try:
        result = run_campaign(
            Path(args.target),
            defect_ids=args.defects,
            stages=stages,
            publish=args.publish,
            skip_repair_if_green=not args.force_repair,
            discovery_report_dir=args.discovery_report,
            impact_receipt_dirs=args.impact_receipts,
        )
    except CampaignRefused as exc:
        print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(f"verdict={result['verdict']} ok={result['ok']} digest={result['campaign_digest'][:16]}...")
        print(f"campaign_dir={result['campaign_dir']}")
        for stage, sr in (result.get("stage_results") or {}).items():
            print(f"  {stage}: {sr.get('verdict')} ok={sr.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
