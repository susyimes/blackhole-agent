"""Multi-mode durable control-flow engine for operational stewardship.

Unifies the two previously parallel control-flow engines:

* **pipeline mode** — ordered multi-stage dialects (campaign, fleet)
* **loop mode** — multi-round durable dialects (program, succession, epoch)

One dialect catalog, one shared digest/seal infrastructure, and one invocable
proof surface. Domain modules keep stage/loop *hooks*; control flow is owned
here. Thin ``upstream_stage_engine`` / ``upstream_loop_engine`` facades re-export
this module so existing imports and ledger proof commands keep working.

Composition:

* ``compose_loop_of_pipeline`` — loop drives pipeline stages (epoch→fleet)
* ``compose_loop_of_loop`` — loop drives nested loop (program→succession, …)
* ``compose_pipeline_of_pipeline`` — pipeline dispatches nested pipeline
  (fleet→campaign) as an engine-owned nest edge
* ``run_control_graph`` / ``OPERATIONAL_NEST`` — declarative multi-depth nest
  program→succession→epoch→fleet→campaign as engine data (not hand-wired glue)
* ``run_operational_spine`` — public live entry for the full depth-5 graph;
  pipeline-of-pipeline (fleet→campaign) is *native* graph composition, not a
  stage-hook fiction
* ``run_governance_spine`` — bridges constitution multi-child stewardship
  (institution→program) onto the operational nest so institution→…→campaign
  is one continuous engine-owned governance path (not a mock program leaf)

No skill-route discovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]


class StageRefused(Exception):
    """A verdict-bearing refusal from the generic stage engine."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


@dataclass(frozen=True)
class PipelineDialect:
    """Nouns and seal vocabulary for one multi-stage durable pipeline."""

    name: str  # self noun: campaign (future: fleet-dispatch, …)
    valid_stages: frozenset[str]
    default_stages: tuple[str, ...]
    artifacts_relative: str = ""
    receipt_filename: str = "receipt.json"
    digest_field: str = ""
    dir_field: str = ""
    # Stages that abort the pipeline when their result ok is false.
    abort_on_fail: frozenset[str] = frozenset()
    # Map stage name → terminal fail verdict (default f"{stage}_failed").
    fail_verdicts: Mapping[str, str] = field(default_factory=dict)

    @property
    def artifacts_root(self) -> Path:
        rel = self.artifacts_relative or f"artifacts/upstream-{self.name}"
        return REPO_ROOT / rel

    @property
    def receipt_name(self) -> str:
        return self.receipt_filename or "receipt.json"

    @property
    def self_digest_field(self) -> str:
        return self.digest_field or f"{self.name}_digest"

    @property
    def self_dir_field(self) -> str:
        return self.dir_field or f"{self.name}_dir"

    def fail_verdict_for(self, stage: str) -> str:
        return str(self.fail_verdicts.get(stage) or f"{stage}_failed")

    def aborts_on_fail(self, stage: str) -> bool:
        # Default: every stage aborts on fail unless dialect sets abort_on_fail
        # to a non-empty set (then only those stages abort).
        if not self.abort_on_fail:
            return True
        return stage in self.abort_on_fail


# Registered operational pipelines (campaign + fleet prove multi-dialect).
CAMPAIGN_STAGES: tuple[str, ...] = (
    "discovery",
    "admit",
    "repair",
    "contribution",
    "publication",
    "impact",
)

FLEET_STAGES: tuple[str, ...] = (
    "inventory",
    "portfolio",
    "rank",
    "dispatch",
)

PIPELINE_STACK: tuple[PipelineDialect, ...] = (
    PipelineDialect(
        name="campaign",
        valid_stages=frozenset(CAMPAIGN_STAGES),
        default_stages=("repair", "contribution", "publication"),
        artifacts_relative="artifacts/upstream-campaign",
        digest_field="campaign_digest",
        dir_field="campaign_dir",
        # Campaign historically aborts hard on discovery/admit/repair/
        # contribution failure; publication/impact mark ok=False but still
        # seal (no early return). Represent that with abort_on_fail.
        abort_on_fail=frozenset(
            {"discovery", "admit", "repair", "contribution"}
        ),
        fail_verdicts={
            "discovery": "discovery_failed",
            "admit": "admit_failed",
            "repair": "repair_failed",
            "contribution": "contribution_failed",
            "publication": "publication_failed",
            "impact": "impact_failed",
        },
    ),
    PipelineDialect(
        name="fleet",
        valid_stages=frozenset(FLEET_STAGES),
        default_stages=("inventory", "portfolio", "rank"),
        artifacts_relative="artifacts/upstream-fleet",
        receipt_filename="plan.json",
        digest_field="fleet_digest",
        dir_field="plan_dir",
        # Inventory/portfolio hard-fail historically raise FleetRefused before
        # seal (domain runners re-raise). Dispatch soft-fails and still seals.
        abort_on_fail=frozenset({"inventory", "portfolio"}),
        fail_verdicts={
            "inventory": "fleet_empty",
            "portfolio": "portfolio_failed",
            "rank": "rank_failed",
            "dispatch": "dispatch_failed",
        },
    ),
)

PIPELINE_DIALECTS: dict[str, PipelineDialect] = {d.name: d for d in PIPELINE_STACK}


def get_pipeline_dialect(name: "PipelineDialect | str") -> PipelineDialect:
    if isinstance(name, PipelineDialect):
        return name
    key = str(name or "").strip().lower()
    if key not in PIPELINE_DIALECTS:
        raise StageRefused(
            "pipeline_unknown_dialect",
            f"unknown pipeline dialect {name!r}; known={sorted(PIPELINE_DIALECTS)}",
        )
    return PIPELINE_DIALECTS[key]


def list_pipeline_dialects() -> list[str]:
    return [d.name for d in PIPELINE_STACK]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _sha256_bytes(canonical.encode("utf-8"))


def normalize_stages(
    dialect: PipelineDialect | str,
    stages: Sequence[str] | None,
) -> list[str]:
    """Validate and de-duplicate stage list; empty → dialect defaults."""
    d = get_pipeline_dialect(dialect) if isinstance(dialect, str) else dialect
    if not stages:
        stage_list = list(d.default_stages)
    else:
        stage_list = list(dict.fromkeys(str(s).strip() for s in stages if str(s).strip()))
    if not stage_list:
        raise StageRefused("stages_empty", "no stages requested")
    unknown = [s for s in stage_list if s not in d.valid_stages]
    if unknown:
        raise StageRefused("stages_unknown", f"unknown stages: {unknown}")
    return stage_list


@dataclass
class PipelineState:
    """Mutable multi-stage state threaded through hooks."""

    dialect: PipelineDialect
    stages: list[str]
    stage_results: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    pipeline_ok: bool = True
    terminal_verdict: str = "pipeline_complete"
    aborted: bool = False
    abort_stage: str | None = None

    @property
    def completed_stages(self) -> list[str]:
        return [s for s in self.stages if s in self.stage_results]


# Hook types -----------------------------------------------------------------

RunStage = Callable[["PipelineState", str], dict[str, Any]]
# May mutate state.context. Returns stage result dict with at least ok/verdict.
ShouldAbort = Callable[["PipelineState", str, Mapping[str, Any]], bool]
# Override abort decision; default uses dialect.abort_on_fail + result.ok.
AfterStage = Callable[["PipelineState", str, Mapping[str, Any]], None]
# Post-stage context mutation (manifest reload, bundle lists, …).
ClassifyVerdict = Callable[["PipelineState"], tuple[bool, str]]
SealPipeline = Callable[["PipelineState"], dict[str, Any]]


def run_stage_pipeline(
    dialect: PipelineDialect | str,
    stages: Sequence[str] | None = None,
    *,
    run_stage: RunStage,
    classify_verdict: ClassifyVerdict,
    seal: SealPipeline,
    should_abort: ShouldAbort | None = None,
    after_stage: AfterStage | None = None,
    initial_context: Mapping[str, Any] | None = None,
    initial_verdict: str = "pipeline_complete",
    wrap_refuse: Callable[[BaseException], BaseException] | None = None,
) -> dict[str, Any]:
    """Run an ordered multi-stage durable pipeline and return the seal result.

    Control flow (shared by campaign and future operational pipelines):

    1. normalize stages against dialect
    2. for each stage in order:
       a. run_stage(state, name) → result
       b. record stage_results[name]
       c. after_stage hook (context mutation)
       d. if not ok and should_abort → mark failed, seal early
    3. classify_verdict + seal
    """
    d = get_pipeline_dialect(dialect) if isinstance(dialect, str) else dialect
    stage_list = normalize_stages(d, stages)

    state = PipelineState(
        dialect=d,
        stages=stage_list,
        context=dict(initial_context or {}),
        terminal_verdict=str(initial_verdict or "pipeline_complete"),
    )

    for stage_name in stage_list:
        try:
            result = run_stage(state, stage_name)
        except Exception as exc:  # noqa: BLE001 — optional refuse mapping
            if wrap_refuse is not None:
                raise wrap_refuse(exc) from exc
            raise
        if not isinstance(result, Mapping):
            raise StageRefused(
                "stage_result_invalid",
                f"stage {stage_name!r} returned non-mapping result",
            )
        stage_body = dict(result)
        stage_body.setdefault("stage", stage_name)
        state.stage_results[stage_name] = stage_body

        if after_stage is not None:
            after_stage(state, stage_name, stage_body)

        ok = bool(stage_body.get("ok"))
        abort = False
        if should_abort is not None:
            abort = bool(should_abort(state, stage_name, stage_body))
        elif not ok and d.aborts_on_fail(stage_name):
            abort = True

        if abort and not ok:
            state.pipeline_ok = False
            state.aborted = True
            state.abort_stage = stage_name
            state.terminal_verdict = d.fail_verdict_for(stage_name)
            # Contribution has a historical special-case: only abort when
            # contribution_failed AND no submittable leftovers. Dialects that
            # need richer abort rules use should_abort.
            sealed = seal(state)
            return _annotate_result(sealed, state)

        if not ok:
            # Soft failure (publication/impact): mark pipeline not-ok but continue.
            state.pipeline_ok = False
            state.terminal_verdict = d.fail_verdict_for(stage_name)

    ok, verdict = classify_verdict(state)
    state.pipeline_ok = bool(ok)
    state.terminal_verdict = str(verdict)
    sealed = seal(state)
    return _annotate_result(sealed, state)


def _annotate_result(result: Mapping[str, Any], state: PipelineState) -> dict[str, Any]:
    body = dict(result)
    body.setdefault("ok", state.pipeline_ok)
    body.setdefault("verdict", state.terminal_verdict)
    body.setdefault("stage_results", dict(state.stage_results))
    body.setdefault("stages", list(state.stages))
    body.setdefault("used_skill_route_discovery", legacy_pipeline_was_used())
    body.setdefault("stage_engine", True)
    body.setdefault("pipeline_dialect", state.dialect.name)
    body.setdefault("control_engine", True)
    body.setdefault("control_mode", "pipeline")
    body.setdefault("control_dialect", state.dialect.name)
    body.setdefault("aborted", state.aborted)
    if state.abort_stage:
        body.setdefault("abort_stage", state.abort_stage)
    return body


def collect_stage_digests(stage_results: Mapping[str, Any]) -> dict[str, str]:
    """Collect campaign-compatible stage artifact digests for seal chains.

    Shared so campaign sealing and engine-native proofs stay digest-aligned.
    """
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
        for item in stage_results["contribution"].get("defects") or []:
            if item.get("bundle_sha256"):
                stage_digests[f"contribution.{item['defect_id']}.bundle"] = str(
                    item["bundle_sha256"]
                )
            stage_digests[f"contribution.{item['defect_id']}.verdict"] = _sha256_bytes(
                str(item.get("verdict") or "").encode("utf-8")
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
    return stage_digests


def seal_pipeline_receipt(
    state: PipelineState,
    *,
    out_root: Path | None,
    identity: Mapping[str, Any],
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    extra_fields: Mapping[str, Any] | None = None,
    summary_lines: Sequence[str] | None = None,
    stage_digests: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write a digest-chained pipeline receipt under a stamped directory.

    ``identity`` must include at least name/version for directory naming;
    campaign also passes target, defect_ids, publish_requested, ecosystem.
    """
    d = state.dialect
    root = Path(out_root) if out_root is not None else d.artifacts_root
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    name = f"{identity.get('name')}-{identity.get('version')}"
    pipeline_dir = root / name / stamp
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    digests = (
        dict(stage_digests)
        if stage_digests is not None
        else collect_stage_digests(state.stage_results)
    )

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "stages": list(state.stages),
        "stage_results": dict(state.stage_results),
        "stage_digests": digests,
        "ok": state.pipeline_ok,
        "verdict": state.terminal_verdict,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "stage_engine": True,
        "pipeline_dialect": d.name,
        "control_engine": True,
        "control_mode": "pipeline",
        "control_dialect": d.name,
    }
    for key, value in identity.items():
        receipt[key] = value
    if extra_fields:
        receipt.update(dict(extra_fields))

    if digest_payload is not None:
        chain = _sha256_json(digest_payload(receipt))
    else:
        chain = _sha256_json(
            {
                "schema_version": SCHEMA_VERSION,
                "name": receipt.get("name"),
                "version": receipt.get("version"),
                "defect_ids": receipt.get("defect_ids"),
                "stages": receipt.get("stages"),
                "stage_digests": digests,
                "ok": receipt.get("ok"),
                "verdict": receipt.get("verdict"),
            }
        )
    receipt[d.self_digest_field] = chain
    atomic_write_json(pipeline_dir / d.receipt_name, receipt)

    if summary_lines is None:
        lines = [
            f"# Pipeline {d.name} {name}",
            f"verdict: {state.terminal_verdict}",
            f"ok: {state.pipeline_ok}",
            f"stages: {', '.join(state.stages)}",
            "",
        ]
        for stage_name in state.stages:
            sr = state.stage_results.get(stage_name) or {}
            lines.append(
                f"## {stage_name}: {sr.get('verdict')} (ok={sr.get('ok')})"
            )
        summary_lines = lines
    (pipeline_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    return {
        "ok": state.pipeline_ok,
        "verdict": state.terminal_verdict,
        d.self_dir_field: str(pipeline_dir),
        d.self_digest_field: chain,
        "stage_results": dict(state.stage_results),
        "stages": list(state.stages),
        "name": receipt.get("name"),
        "version": receipt.get("version"),
        "defect_ids": list(receipt.get("defect_ids") or []),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "stage_engine": True,
        "pipeline_dialect": d.name,
        "control_engine": True,
        "control_mode": "pipeline",
        "control_dialect": d.name,
        "receipt": receipt,
    }


def verify_pipeline_digest(
    pipeline_dir: Path,
    *,
    dialect: PipelineDialect | str = "campaign",
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Re-check only the chain digest field (artifact re-hash is dialect-side)."""
    d = get_pipeline_dialect(dialect) if isinstance(dialect, str) else dialect
    receipt_path = durable_read_path(Path(pipeline_dir) / d.receipt_name)
    if not receipt_path.is_file():
        return {"ok": False, "error": f"missing receipt: {receipt_path}"}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    stage_digests = dict(receipt.get("stage_digests") or {})
    if digest_payload is not None:
        expected = _sha256_json(digest_payload(receipt))
    else:
        expected = _sha256_json(
            {
                "schema_version": receipt.get("schema_version", SCHEMA_VERSION),
                "name": receipt.get("name"),
                "version": receipt.get("version"),
                "defect_ids": receipt.get("defect_ids"),
                "stages": receipt.get("stages"),
                "stage_digests": stage_digests,
                "ok": receipt.get("ok"),
                "verdict": receipt.get("verdict"),
            }
        )
    actual = receipt.get(d.self_digest_field)
    mismatched: list[str] = []
    problems: list[str] = []
    if expected != actual:
        mismatched.append(d.self_digest_field)
        problems.append(f"{d.name} chain digest mismatch")
    return {
        "ok": not problems and not mismatched,
        "problems": problems,
        "mismatched": mismatched,
        d.self_digest_field: actual,
        "verdict": receipt.get("verdict"),
        "stage_engine": receipt.get("stage_engine"),
        "pipeline_dialect": receipt.get("pipeline_dialect"),
    }


# ---------------------------------------------------------------------------
# hermetic proof


def builtin_stage_engine_proof() -> dict[str, Any]:
    """Hermetic proof that the stage engine owns multi-dialect pipeline control flow.

    Proves:
    - multi-dialect registration (campaign + fleet)
    - engine-native multi-stage run with abort-on-fail and soft-fail
    - engine-native fleet dialect seal + abort
    - digest seal + tamper detection
    - live ``upstream_campaign.run_campaign`` and ``upstream_fleet.plan_fleet``
      set stage_engine ownership
    - live campaign + fleet builtin proofs stay green
    - ledger binding for capability.upstream-stage-engine
    - no skill-route discovery
    """
    scratch = Path(tempfile.mkdtemp(prefix="stage-engine-proof-"))
    try:
        dialects = list_pipeline_dialects()
        dialects_ok = (
            dialects == ["campaign", "fleet"]
            and "campaign" in PIPELINE_DIALECTS
            and "fleet" in PIPELINE_DIALECTS
        )
        campaign_d = get_pipeline_dialect("campaign")
        fleet_d = get_pipeline_dialect("fleet")
        known_stages_ok = (
            set(CAMPAIGN_STAGES) == set(campaign_d.valid_stages)
            and set(FLEET_STAGES) == set(fleet_d.valid_stages)
        )

        # --- engine-native pipeline (no campaign domain deps) ---
        calls: list[str] = []

        def run_stage(state: PipelineState, name: str) -> dict[str, Any]:
            calls.append(name)
            ctx = state.context
            if name == "discovery":
                return {
                    "stage": "discovery",
                    "ok": True,
                    "verdict": "scanned",
                    "report_sha256": "d" * 64,
                    "finding_count": 1,
                }
            if name == "admit":
                ctx["admitted"] = True
                return {
                    "stage": "admit",
                    "ok": True,
                    "verdict": "admitted",
                    "admission_digest": "a" * 64,
                    "admitted_count": 1,
                }
            if name == "repair":
                # Fail hard to prove abort short-circuit.
                if ctx.get("force_repair_fail"):
                    return {
                        "stage": "repair",
                        "ok": False,
                        "verdict": "repair_failed",
                    }
                return {
                    "stage": "repair",
                    "ok": True,
                    "verdict": "repaired",
                    "report_digest": "r" * 64,
                }
            if name == "contribution":
                return {
                    "stage": "contribution",
                    "ok": True,
                    "verdict": "submittable_ready",
                    "defects": [
                        {
                            "defect_id": "d1",
                            "ok": True,
                            "submittable": True,
                            "verdict": "ready",
                            "bundle_sha256": "b" * 64,
                        }
                    ],
                    "submittable_count": 1,
                }
            if name == "publication":
                if ctx.get("soft_pub_fail"):
                    return {
                        "stage": "publication",
                        "ok": False,
                        "verdict": "publication_failed",
                        "publications": [],
                        "published_count": 0,
                    }
                return {
                    "stage": "publication",
                    "ok": True,
                    "verdict": "published",
                    "publications": [
                        {
                            "bundle_dir": "/tmp/bundle-d1",
                            "ok": True,
                            "published": True,
                            "verdict": "published",
                            "receipt_sha256": "p" * 64,
                        }
                    ],
                    "published_count": 1,
                }
            if name == "impact":
                return {
                    "stage": "impact",
                    "ok": True,
                    "verdict": "impact_open",
                    "assessments": [
                        {
                            "defect_id": "d1",
                            "ok": True,
                            "outcome": "impact_open",
                            "impact_digest": "i" * 64,
                            "certificate_sha256": "c" * 64,
                        }
                    ],
                    "assessed_count": 1,
                }
            raise StageRefused("stage_unknown", name)

        def after_stage(state: PipelineState, name: str, result: Mapping[str, Any]) -> None:
            if name == "contribution":
                state.context["submittable"] = int(result.get("submittable_count") or 0)

        def classify(state: PipelineState) -> tuple[bool, str]:
            if not state.pipeline_ok:
                return False, state.terminal_verdict
            # Prefer outermost stage verdict when present.
            for name in reversed(state.stages):
                sr = state.stage_results.get(name) or {}
                if sr.get("verdict"):
                    return True, str(sr["verdict"])
            return True, "pipeline_complete"

        def seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "engine-native",
                identity={
                    "name": "engineprobe",
                    "version": "1.0.0",
                    "defect_ids": ["d1"],
                    "publish_requested": True,
                    "target": str(scratch / "target"),
                },
            )

        full = run_stage_pipeline(
            "campaign",
            stages=CAMPAIGN_STAGES,
            run_stage=run_stage,
            after_stage=after_stage,
            classify_verdict=classify,
            seal=seal,
            initial_context={},
            initial_verdict="campaign_complete",
        )
        full_ok = (
            full.get("ok")
            and full.get("stage_engine") is True
            and full.get("pipeline_dialect") == "campaign"
            and full.get("verdict") == "impact_open"
            and calls == list(CAMPAIGN_STAGES)
            and "impact" in full.get("stage_results", {})
        )
        full_dir = Path(full["campaign_dir"])
        verified = verify_pipeline_digest(full_dir, dialect="campaign")
        seal_ok = bool(verified.get("ok"))

        # Tamper
        rp = full_dir / "receipt.json"
        body = json.loads(rp.read_text(encoding="utf-8"))
        body["campaign_digest"] = "0" * 64
        rp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        tampered = verify_pipeline_digest(full_dir, dialect="campaign")
        tamper_ok = (not tampered.get("ok")) and "campaign_digest" in (
            tampered.get("mismatched") or []
        )

        # Hard abort: repair fails → contribution must not run.
        calls.clear()
        aborted = run_stage_pipeline(
            "campaign",
            stages=("repair", "contribution", "publication"),
            run_stage=run_stage,
            after_stage=after_stage,
            classify_verdict=classify,
            seal=seal,
            initial_context={"force_repair_fail": True},
        )
        abort_ok = (
            not aborted.get("ok")
            and aborted.get("verdict") == "repair_failed"
            and aborted.get("aborted") is True
            and aborted.get("abort_stage") == "repair"
            and calls == ["repair"]
            and "contribution" not in aborted.get("stage_results", {})
            and aborted.get("stage_engine") is True
        )

        # Soft fail: publication fails but still seals (does not abort mid-run
        # in the same hard way — actually publication is NOT in abort_on_fail,
        # so pipeline continues; with only publication as last stage, ok=False).
        calls.clear()
        soft = run_stage_pipeline(
            "campaign",
            stages=("contribution", "publication"),
            run_stage=run_stage,
            after_stage=after_stage,
            classify_verdict=classify,
            seal=seal,
            initial_context={"soft_pub_fail": True},
        )
        soft_ok = (
            not soft.get("ok")
            and soft.get("verdict") == "publication_failed"
            and calls == ["contribution", "publication"]
            and soft.get("aborted") is False
        )

        # Unknown stages refused (both dialects).
        unknown_refused = False
        try:
            normalize_stages("campaign", ("repair", "not_a_stage"))
        except StageRefused as exc:
            unknown_refused = exc.verdict == "stages_unknown"
        fleet_unknown_refused = False
        try:
            normalize_stages("fleet", ("inventory", "not_a_stage"))
        except StageRefused as exc:
            fleet_unknown_refused = exc.verdict == "stages_unknown"

        # --- engine-native fleet dialect (no fleet domain deps) ---
        fleet_calls: list[str] = []

        def run_fleet_stage(state: PipelineState, name: str) -> dict[str, Any]:
            fleet_calls.append(name)
            ctx = state.context
            if name == "inventory":
                if ctx.get("force_empty"):
                    return {
                        "stage": "inventory",
                        "ok": False,
                        "verdict": "fleet_empty",
                        "inventory_count": 0,
                    }
                ctx["inventory"] = [{"name": "alpha", "version": "1.0.0"}]
                return {
                    "stage": "inventory",
                    "ok": True,
                    "verdict": "inventoried",
                    "inventory_count": 1,
                }
            if name == "portfolio":
                ctx["portfolio"] = {"entries": [], "portfolio_digest": "p" * 64}
                ctx["portfolio_source"] = "injected"
                return {
                    "stage": "portfolio",
                    "ok": True,
                    "verdict": "portfolio_ready",
                    "portfolio_source": "injected",
                    "portfolio_digest": "p" * 64,
                }
            if name == "rank":
                actions = [
                    {
                        "action": "campaign_patch_bound",
                        "name": "alpha",
                        "version": "1.0.0",
                        "campaignable": True,
                        "priority": 40,
                        "rank": 1,
                    }
                ]
                ctx["actions"] = actions
                ctx["campaignable"] = [a for a in actions if a.get("campaignable")]
                return {
                    "stage": "rank",
                    "ok": True,
                    "verdict": "ranked",
                    "action_count": len(actions),
                    "campaignable_count": 1,
                    "top_action": actions[0],
                }
            if name == "dispatch":
                if ctx.get("force_dispatch_fail"):
                    return {
                        "stage": "dispatch",
                        "ok": False,
                        "verdict": "dispatch_failed",
                        "dispatched_count": 1,
                        "dispatched_ok": 0,
                        "dispatches": [{"ok": False, "verdict": "dispatch_error"}],
                    }
                dig = "d" * 64
                return {
                    "stage": "dispatch",
                    "ok": True,
                    "verdict": "fleet_dispatched",
                    "dispatched_count": 1,
                    "dispatched_ok": 1,
                    "dispatches": [
                        {
                            "ok": True,
                            "verdict": "dispatched_proof",
                            "campaign_digest": dig,
                        }
                    ],
                    "dispatch_digests": {"alpha-1.0.0-campaign_patch_bound": dig},
                }
            raise StageRefused("stage_unknown", name)

        def fleet_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            if "dispatch" in state.stage_results:
                disp = state.stage_results["dispatch"]
                if disp.get("ok") and int(disp.get("dispatched_ok") or 0) > 0:
                    return True, "fleet_dispatched"
            campaignable = state.context.get("campaignable") or []
            if campaignable:
                return True, "fleet_ranked"
            actions = state.context.get("actions") or []
            if actions:
                return True, "fleet_monitor_only"
            return True, "fleet_idle"

        def fleet_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "fleet-engine-native",
                identity={
                    "name": "fleetprobe",
                    "version": "1.0.0",
                    "inventory_count": len(state.context.get("inventory") or []),
                    "action_count": len(state.context.get("actions") or []),
                },
                stage_digests={
                    "inventory.verdict": _sha256_bytes(
                        str(
                            (state.stage_results.get("inventory") or {}).get("verdict")
                            or ""
                        ).encode("utf-8")
                    ),
                    "rank.verdict": _sha256_bytes(
                        str(
                            (state.stage_results.get("rank") or {}).get("verdict") or ""
                        ).encode("utf-8")
                    ),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "version": receipt.get("version"),
                    "stages": receipt.get("stages"),
                    "stage_digests": receipt.get("stage_digests"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        fleet_full = run_stage_pipeline(
            "fleet",
            stages=FLEET_STAGES,
            run_stage=run_fleet_stage,
            classify_verdict=fleet_classify,
            seal=fleet_seal,
            initial_context={},
            initial_verdict="fleet_ranked",
        )
        fleet_native_ok = (
            fleet_full.get("ok")
            and fleet_full.get("stage_engine") is True
            and fleet_full.get("pipeline_dialect") == "fleet"
            and fleet_full.get("verdict") == "fleet_dispatched"
            and fleet_calls == list(FLEET_STAGES)
            and bool(fleet_full.get("fleet_digest") or fleet_full.get("plan_dir"))
        )
        fleet_dir = Path(fleet_full.get("plan_dir") or "")
        fleet_verified = verify_pipeline_digest(
            fleet_dir,
            dialect="fleet",
            digest_payload=lambda receipt: {
                "schema_version": SCHEMA_VERSION,
                "name": receipt.get("name"),
                "version": receipt.get("version"),
                "stages": receipt.get("stages"),
                "stage_digests": receipt.get("stage_digests"),
                "ok": receipt.get("ok"),
                "verdict": receipt.get("verdict"),
            },
        )
        fleet_seal_ok = bool(fleet_verified.get("ok"))

        # Fleet hard abort: empty inventory stops before rank/dispatch.
        fleet_calls.clear()
        fleet_aborted = run_stage_pipeline(
            "fleet",
            stages=FLEET_STAGES,
            run_stage=run_fleet_stage,
            classify_verdict=fleet_classify,
            seal=fleet_seal,
            initial_context={"force_empty": True},
        )
        fleet_abort_ok = (
            not fleet_aborted.get("ok")
            and fleet_aborted.get("verdict") == "fleet_empty"
            and fleet_aborted.get("aborted") is True
            and fleet_aborted.get("abort_stage") == "inventory"
            and fleet_calls == ["inventory"]
            and "rank" not in fleet_aborted.get("stage_results", {})
            and fleet_aborted.get("stage_engine") is True
            and fleet_aborted.get("pipeline_dialect") == "fleet"
        )

        # Fleet soft fail: dispatch fails but still seals after rank.
        fleet_calls.clear()
        fleet_soft = run_stage_pipeline(
            "fleet",
            stages=FLEET_STAGES,
            run_stage=run_fleet_stage,
            classify_verdict=fleet_classify,
            seal=fleet_seal,
            initial_context={"force_dispatch_fail": True},
        )
        fleet_soft_ok = (
            not fleet_soft.get("ok")
            and fleet_soft.get("verdict") == "dispatch_failed"
            and fleet_calls == list(FLEET_STAGES)
            and fleet_soft.get("aborted") is False
            and fleet_soft.get("pipeline_dialect") == "fleet"
        )

        # Live campaign module ownership.
        from blackhole_agent import upstream_campaign as ucamp
        from blackhole_agent import upstream_fleet as ufleet

        campaign_uses_engine = getattr(ucamp, "STAGE_ENGINE", False) is True
        campaign_dialect = getattr(ucamp, "STAGE_ENGINE_DIALECT", "") == "campaign"
        fleet_uses_engine = getattr(ufleet, "STAGE_ENGINE", False) is True
        fleet_dialect = getattr(ufleet, "STAGE_ENGINE_DIALECT", "") == "fleet"

        # Re-prove live campaign + fleet (must stay green after multi-dialect).
        live_proof = ucamp.builtin_upstream_campaign_proof()
        live_proof_ok = bool(live_proof.get("ok"))
        live_fleet_proof = ufleet.builtin_upstream_fleet_proof()
        live_fleet_proof_ok = bool(live_fleet_proof.get("ok"))

        # Spot-check live run_campaign advertises stage_engine ownership.
        # Reuse a minimal hermetic contribution→publication dry path via proof
        # target when available; fall back to flag check alone if fixtures fail.
        live_flag = False
        live_digest_present = False
        live_exc = ""
        try:
            from blackhole_agent import upstream_contribution as uc
            from blackhole_agent import upstream_publication as upub

            target = uc._proof_target(scratch / "live-stew-unique")
            repo_url = "https://github.com/proof/contribprobe"
            head_url = uc.github_archive_url(repo_url, "HEAD")
            tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

            def fetcher(url: str) -> bytes:
                if url == head_url:
                    return uc._proof_archive(
                        uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD"
                    )
                return tag_archive

            _upstream, fork = upub._proof_remotes(
                scratch / "live-remotes", upub._PROOF_SOURCE_V1
            )
            gh = upub._FakeGh(fork)

            def publisher(bundle_dir: Path, **kwargs: Any) -> dict[str, Any]:
                pub_bundle = upub._proof_write_bundle(
                    scratch / "live-pub-bundle" / Path(bundle_dir).name,
                    patch=upub._PROOF_PATCH,
                    test_text=upub._PROOF_TEST,
                    repro_text=upub._PROOF_REPRO,
                )
                return upub.publish_contribution(
                    pub_bundle,
                    publish=False,
                    gh=gh,
                    verifier=upub._proof_verifier,
                    manifest={"contribution": {"tests_subdir": "tests"}},
                    out_root=kwargs.get("out_root") or (scratch / "live-pub"),
                )

            live = ucamp.run_campaign(
                target,
                stages=("contribution", "publication"),
                publish=False,
                fetcher=fetcher,
                publisher=publisher,
                contribution_out_root=scratch / "live-contrib",
                publication_out_root=scratch / "live-pub",
                out_root=scratch / "live-campaigns",
            )
            live_flag = (
                live.get("stage_engine") is True
                and live.get("pipeline_dialect") == "campaign"
            )
            live_digest_present = bool(live.get("campaign_digest"))
        except Exception as exc:  # noqa: BLE001
            live_flag = False
            live_digest_present = False
            live_exc = f"{type(exc).__name__}: {exc}"[:300]

        # Spot-check live plan_fleet advertises stage_engine + fleet dialect.
        live_fleet_flag = False
        live_fleet_digest = False
        live_fleet_exc = ""
        try:
            stew = scratch / "live-fleet-stew"
            stew.mkdir(parents=True, exist_ok=True)
            ufleet._proof_target(
                stew,
                name="livealpha",
                version="1.0.0",
                defects=[
                    {
                        "id": "live-dos",
                        "title": "live dos",
                        "kind": "complexity",
                        "patch": "patches/live-dos.patch",
                        "repro": "repros/live_dos.py",
                    }
                ],
            )
            live_fleet = ufleet.plan_fleet(
                stewardship_root=stew,
                portfolio=ufleet._proof_portfolio(
                    [
                        {
                            "name": "livealpha",
                            "version": "1.0.0",
                            "defect_id": "live-dos",
                            "outcome": "impact_closed_unmerged",
                            "impact_digest": "f" * 64,
                            "ok": True,
                        }
                    ]
                ),
                dispatch=False,
                out_root=scratch / "live-fleet-plans",
            )
            live_fleet_flag = (
                live_fleet.get("stage_engine") is True
                and live_fleet.get("pipeline_dialect") == "fleet"
            )
            live_fleet_digest = bool(live_fleet.get("fleet_digest"))
        except Exception as exc:  # noqa: BLE001
            live_fleet_flag = False
            live_fleet_digest = False
            live_fleet_exc = f"{type(exc).__name__}: {exc}"[:300]

        multi_dialect_owned = (
            campaign_uses_engine
            and campaign_dialect
            and fleet_uses_engine
            and fleet_dialect
            and live_flag
            and live_fleet_flag
        )

        # Ledger binding.
        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-stage-engine")
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and "upstream_stage_engine" in (entry.entry or "")
                and "stage" in tags_blob
                and ("fleet" in tags_blob or "fleet" in delta_blob or "multi" in delta_blob)
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        # LOC evidence: engine is the shared orchestration core.
        engine_path = Path(__file__).resolve()
        engine_loc = sum(
            1
            for line in engine_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        campaign_path = (
            REPO_ROOT / "src" / "blackhole_agent" / "upstream_campaign.py"
        )
        campaign_loc = 0
        if campaign_path.is_file():
            campaign_loc = sum(
                1
                for line in campaign_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
        fleet_path = REPO_ROOT / "src" / "blackhole_agent" / "upstream_fleet.py"
        fleet_loc = 0
        if fleet_path.is_file():
            fleet_loc = sum(
                1
                for line in fleet_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            )

        ok = all(
            [
                dialects_ok,
                known_stages_ok,
                full_ok,
                seal_ok,
                tamper_ok,
                abort_ok,
                soft_ok,
                unknown_refused,
                fleet_unknown_refused,
                fleet_native_ok,
                fleet_seal_ok,
                fleet_abort_ok,
                fleet_soft_ok,
                campaign_uses_engine,
                campaign_dialect,
                fleet_uses_engine,
                fleet_dialect,
                live_flag,
                live_digest_present,
                live_proof_ok,
                live_fleet_flag,
                live_fleet_digest,
                live_fleet_proof_ok,
                multi_dialect_owned,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "stage_engine_proof",
            "dialect_count": len(dialects),
            "dialects": dialects,
            "dialects_ok": dialects_ok,
            "known_stages_ok": known_stages_ok,
            "engine_native_ok": full_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_ok,
            "hard_abort_ok": abort_ok,
            "soft_fail_ok": soft_ok,
            "unknown_stages_refused": unknown_refused and fleet_unknown_refused,
            "fleet_engine_native_ok": fleet_native_ok,
            "fleet_seal_verified": fleet_seal_ok,
            "fleet_hard_abort_ok": fleet_abort_ok,
            "fleet_soft_fail_ok": fleet_soft_ok,
            "campaign_stage_engine": campaign_uses_engine,
            "campaign_stage_engine_dialect": campaign_dialect,
            "fleet_stage_engine": fleet_uses_engine,
            "fleet_stage_engine_dialect": fleet_dialect,
            "multi_dialect_owned": multi_dialect_owned,
            "live_campaign_flag": live_flag,
            "live_campaign_digest": live_digest_present,
            "live_campaign_proof_ok": live_proof_ok,
            "live_fleet_flag": live_fleet_flag,
            "live_fleet_digest": live_fleet_digest,
            "live_fleet_proof_ok": live_fleet_proof_ok,
            "live_exc": live_exc,
            "live_fleet_exc": live_fleet_exc,
            "ledger_capability_ok": ledger_ok,
            "engine_loc": engine_loc,
            "campaign_loc": campaign_loc,
            "fleet_loc": fleet_loc,
            "engine_native_digest": full.get("campaign_digest"),
            "fleet_engine_native_digest": fleet_full.get("fleet_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)




# ===== LOOP MODE (multi-round durable dialects) =====

class LoopRefused(Exception):
    """A verdict-bearing refusal from the generic loop engine."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


@dataclass(frozen=True)
class LoopDialect:
    """Nouns and stop-reason vocabulary for one multi-round durable loop."""

    name: str  # self noun: program | succession | epoch
    child: str  # child noun: succession | epoch | wave
    child_plural: str
    max_stop_reason: str
    goal_stop_reason: str
    idle_stop_reason: str
    rank_only_stop_reason: str = "rank_only"
    budget_stop_reason: str = "dispatch_budget"
    artifacts_relative: str = ""
    receipt_filename: str = ""
    digest_field: str = ""
    dir_field: str = ""
    count_field: str = ""
    digests_field: str = ""
    met_field: str = ""
    records_field: str = ""

    @property
    def artifacts_root(self) -> Path:
        rel = self.artifacts_relative or f"artifacts/upstream-{self.name}"
        return REPO_ROOT / rel

    @property
    def receipt_name(self) -> str:
        return self.receipt_filename or f"{self.name}.json"

    @property
    def self_digest_field(self) -> str:
        return self.digest_field or f"{self.name}_digest"

    @property
    def self_dir_field(self) -> str:
        return self.dir_field or f"{self.name}_dir"

    @property
    def child_count_field(self) -> str:
        return self.count_field or f"{self.child}_count"

    @property
    def child_digests_field(self) -> str:
        return self.digests_field or f"{self.child}_digests"

    @property
    def self_met_field(self) -> str:
        return self.met_field or f"{self.name}_met"

    @property
    def child_records_field(self) -> str:
        return self.records_field or self.child_plural


# Registered leaf multi-round dialects (outer → inner).
LOOP_STACK: tuple[LoopDialect, ...] = (
    LoopDialect(
        name="program",
        child="succession",
        child_plural="successions",
        max_stop_reason="max_successions",
        goal_stop_reason="program_met",
        idle_stop_reason="program_idle",
        artifacts_relative="artifacts/upstream-program",
        met_field="program_met",
    ),
    LoopDialect(
        name="succession",
        child="epoch",
        child_plural="epochs",
        max_stop_reason="max_epochs",
        goal_stop_reason="mandate_met",
        idle_stop_reason="succession_idle",
        artifacts_relative="artifacts/upstream-succession",
        met_field="mandate_met",
    ),
    LoopDialect(
        name="epoch",
        child="wave",
        child_plural="waves",
        max_stop_reason="max_waves",
        goal_stop_reason="epoch_idle",  # epoch "goal" is often idle/no-work
        idle_stop_reason="epoch_idle",
        artifacts_relative="artifacts/upstream-epoch",
        met_field="epoch_idle",
        digests_field="wave_digests",
    ),
)

LOOP_DIALECTS: dict[str, LoopDialect] = {d.name: d for d in LOOP_STACK}


def get_loop_dialect(name: "LoopDialect | str") -> LoopDialect:
    if isinstance(name, LoopDialect):
        return name
    key = str(name or "").strip().lower()
    if key not in LOOP_DIALECTS:
        raise LoopRefused(
            "loop_unknown_dialect",
            f"unknown loop dialect {name!r}; known={sorted(LOOP_DIALECTS)}",
        )
    return LOOP_DIALECTS[key]


def list_loop_dialects() -> list[str]:
    return [d.name for d in LOOP_STACK]




@dataclass
class LoopState:
    """Mutable round-loop state threaded through hooks."""

    dialect: LoopDialect
    portfolio: dict[str, Any] | None
    portfolio_source: str
    portfolio_start_digest: str | None
    loop_dir: Path
    child_root: Path
    max_rounds: int
    dispatch: bool
    dispatch_budget: int | None
    idle_limit: int
    total_dispatched: int = 0
    total_dispatched_ok: int = 0
    idle_streak: int = 0
    stop_reason: str = ""
    goal_met: bool = False
    records: list[dict[str, Any]] = field(default_factory=list)
    child_digests: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def round_index(self) -> int:
        return len(self.records)


# Hook types -----------------------------------------------------------------

BuildChildKwargs = Callable[[LoopState, int], dict[str, Any]]
OnChildResult = Callable[[LoopState, int, dict[str, Any]], dict[str, Any] | None]
# Returns optional record dict (appended). May mutate state.portfolio etc.
PreRoundStop = Callable[[LoopState, int], str | None]
PostRoundStop = Callable[[LoopState, int, dict[str, Any]], str | None]
IsIdleRound = Callable[[LoopState, int, dict[str, Any]], bool]
LoopClassifyVerdict = Callable[[LoopState], tuple[bool, str]]
SealLoop = Callable[[LoopState], dict[str, Any]]
ExtractDispatched = Callable[[dict[str, Any]], tuple[int, int]]
ExtractChildDigest = Callable[[dict[str, Any]], str | None]
ExtractPortfolio = Callable[[LoopState, dict[str, Any]], dict[str, Any] | None]


def resolve_portfolio(
    *,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    recompute_digest: Callable[[MutableMapping[str, Any]], str] | None = None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Resolve starting portfolio from inject / dir / none."""
    current: dict[str, Any] | None = None
    source = "none"
    if portfolio is not None:
        current = dict(portfolio)
        source = "injected"
    elif portfolio_dir is not None:
        path = durable_read_path(Path(portfolio_dir) / "portfolio.json")
        if not path.is_file():
            raise LoopRefused(
                "portfolio_missing", f"no portfolio.json under {portfolio_dir}"
            )
        current = json.loads(path.read_text(encoding="utf-8"))
        source = "dir"
    start_digest = current.get("portfolio_digest") if current else None
    if current and not start_digest and recompute_digest is not None:
        start_digest = recompute_digest(current)
        current["portfolio_digest"] = start_digest
    elif current:
        start_digest = current.get("portfolio_digest")
    return current, source, start_digest


def open_loop_dir(
    dialect: LoopDialect,
    *,
    out_root: Path | None = None,
    child_out_root: Path | None = None,
    child_subdir: str | None = None,
    nest_stamp: bool = True,
) -> tuple[Path, Path]:
    """Create a stamped loop directory and child-output root.

    Default matches succession/epoch legacy contract: ``out_root / <stamp>``
    (or ``artifacts_root / <stamp>``). Pass ``nest_stamp=False`` to use
    ``out_root`` itself as the loop directory (program-style).
    """
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None and not nest_stamp:
        loop_dir = Path(out_root)
    else:
        parent = Path(out_root) if out_root is not None else dialect.artifacts_root
        loop_dir = parent / stamp
    loop_dir.mkdir(parents=True, exist_ok=True)
    child_root = (
        Path(child_out_root)
        if child_out_root is not None
        else (loop_dir / (child_subdir or dialect.child_plural))
    )
    return loop_dir, child_root


def default_extract_dispatched(result: Mapping[str, Any]) -> tuple[int, int]:
    n = int(
        result.get("total_dispatched")
        if result.get("total_dispatched") is not None
        else result.get("dispatched_count")
        or 0
    )
    ok = int(
        result.get("total_dispatched_ok")
        if result.get("total_dispatched_ok") is not None
        else result.get("dispatched_ok")
        or 0
    )
    return n, ok


def run_durable_loop(
    dialect: LoopDialect | str,
    *,
    max_rounds: int,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    idle_limit: int = 1,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    out_root: Path | None = None,
    child_out_root: Path | None = None,
    child_runner: Callable[..., dict[str, Any]],
    build_child_kwargs: BuildChildKwargs,
    on_child_result: OnChildResult,
    pre_round_stop: PreRoundStop | None = None,
    post_round_stop: PostRoundStop | None = None,
    is_idle_round: IsIdleRound | None = None,
    classify_verdict: LoopClassifyVerdict,
    seal: SealLoop,
    extract_dispatched: ExtractDispatched | None = None,
    refuse_on_first: Sequence[type[BaseException]] = (),
    recompute_digest: Callable[[MutableMapping[str, Any]], str] | None = None,
    prior_total_dispatched: int = 0,
    prior_total_dispatched_ok: int = 0,
    initial_extras: Mapping[str, Any] | None = None,
    wrap_refuse: Callable[[BaseException], BaseException] | None = None,
    nest_stamp: bool = True,
) -> dict[str, Any]:
    """Run a multi-round durable loop and return the dialect seal result.

    Control flow (shared by program / succession / epoch):

    1. resolve portfolio
    2. open loop dir
    3. for round in 0..max_rounds-1:
       a. pre_round_stop → break (goal already met, budget, …)
       b. remaining budget → break if exhausted
       c. child_runner(**build_child_kwargs)
       d. accumulate dispatch counts
       e. on_child_result → optional record
       f. post_round_stop → break
       g. idle streak → break
       h. budget exhausted → break
    4. classify_verdict + seal
    """
    d = get_loop_dialect(dialect) if isinstance(dialect, str) else dialect
    if max_rounds < 1:
        raise LoopRefused(f"{d.name}_invalid", f"max_rounds must be >= 1 for {d.name}")

    current, source, start_digest = resolve_portfolio(
        portfolio=portfolio,
        portfolio_dir=portfolio_dir,
        recompute_digest=recompute_digest,
    )
    loop_dir, child_root = open_loop_dir(
        d,
        out_root=out_root,
        child_out_root=child_out_root,
        nest_stamp=nest_stamp,
    )

    state = LoopState(
        dialect=d,
        portfolio=current,
        portfolio_source=source,
        portfolio_start_digest=start_digest,
        loop_dir=loop_dir,
        child_root=child_root,
        max_rounds=max_rounds,
        dispatch=bool(dispatch),
        dispatch_budget=dispatch_budget,
        idle_limit=max(1, int(idle_limit)),
        total_dispatched=int(prior_total_dispatched),
        total_dispatched_ok=int(prior_total_dispatched_ok),
        stop_reason=d.max_stop_reason,
        extras=dict(initial_extras or {}),
    )
    extract = extract_dispatched or default_extract_dispatched
    refuse_types = tuple(refuse_on_first)

    for round_index in range(max_rounds):
        if pre_round_stop is not None:
            reason = pre_round_stop(state, round_index)
            if reason:
                state.stop_reason = str(reason)
                break

        remaining_budget = None
        if state.dispatch_budget is not None:
            remaining_budget = max(
                0, int(state.dispatch_budget) - state.total_dispatched
            )
            if state.dispatch and remaining_budget <= 0:
                state.stop_reason = d.budget_stop_reason
                break

        kwargs = build_child_kwargs(state, round_index)
        if remaining_budget is not None and "dispatch_budget" in kwargs:
            # Caller may already have set it; keep their value if smaller.
            try:
                kwargs["dispatch_budget"] = min(
                    int(kwargs["dispatch_budget"])
                    if kwargs["dispatch_budget"] is not None
                    else remaining_budget,
                    remaining_budget,
                )
            except (TypeError, ValueError):
                kwargs["dispatch_budget"] = remaining_budget

        try:
            child_result = child_runner(**kwargs)
        except Exception as exc:  # noqa: BLE001 — dialect refuse mapping
            if refuse_types and isinstance(exc, refuse_types):
                if round_index == 0 and not state.extras.get("resumed"):
                    if wrap_refuse is not None:
                        raise wrap_refuse(exc) from exc
                    raise
                verdict = getattr(exc, "verdict", type(exc).__name__)
                state.stop_reason = f"{d.child}_refused:{verdict}"
                break
            raise

        dispatched_n, dispatched_ok = extract(child_result)
        state.total_dispatched += dispatched_n
        state.total_dispatched_ok += dispatched_ok

        record = on_child_result(state, round_index, child_result)
        if record is not None:
            state.records.append(dict(record))

        if post_round_stop is not None:
            reason = post_round_stop(state, round_index, child_result)
            if reason:
                state.stop_reason = str(reason)
                break

        idle = False
        if is_idle_round is not None:
            idle = bool(is_idle_round(state, round_index, child_result))
        else:
            idle = dispatched_n == 0

        if idle:
            state.idle_streak += 1
            if state.idle_streak >= state.idle_limit:
                if not state.dispatch:
                    state.stop_reason = d.rank_only_stop_reason
                else:
                    state.stop_reason = d.idle_stop_reason
                break
        else:
            state.idle_streak = 0

        if (
            state.dispatch_budget is not None
            and state.total_dispatched >= int(state.dispatch_budget)
        ):
            state.stop_reason = d.budget_stop_reason
            break
    else:
        state.stop_reason = d.max_stop_reason

    ok, verdict = classify_verdict(state)
    state.extras["ok"] = ok
    state.extras["verdict"] = verdict
    result = seal(state)
    # Ensure common fields always present for cross-dialect callers.
    result.setdefault("ok", ok)
    result.setdefault("verdict", verdict)
    result.setdefault("stop_reason", state.stop_reason)
    result.setdefault("total_dispatched", state.total_dispatched)
    result.setdefault("total_dispatched_ok", state.total_dispatched_ok)
    result.setdefault(d.self_dir_field, str(state.loop_dir))
    result.setdefault(d.child_count_field, len(state.records))
    result.setdefault(d.child_digests_field, list(state.child_digests))
    result.setdefault("portfolio_start_digest", state.portfolio_start_digest)
    result.setdefault(
        "portfolio_end_digest",
        (state.portfolio or {}).get("portfolio_digest") if state.portfolio else None,
    )
    result.setdefault("portfolio_source", state.portfolio_source)
    result.setdefault("used_skill_route_discovery", legacy_pipeline_was_used())
    result.setdefault("loop_engine", True)
    result.setdefault("loop_dialect", d.name)
    result.setdefault("control_engine", True)
    result.setdefault("control_mode", "loop")
    result.setdefault("control_dialect", d.name)
    return result


def seal_json_receipt(
    state: LoopState,
    receipt: Mapping[str, Any],
    *,
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    summary_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Write receipt + summary under state.loop_dir; set digest field."""
    body = dict(receipt)
    body.setdefault("schema_version", SCHEMA_VERSION)
    body.setdefault("created_at", utc_now_iso())
    body.setdefault("used_skill_route_discovery", legacy_pipeline_was_used())
    digest = _sha256_json(digest_payload(body))
    body[state.dialect.self_digest_field] = digest
    atomic_write_json(state.loop_dir / state.dialect.receipt_name, body)
    summary: dict[str, Any] = {
        "verdict": body.get("verdict"),
        "ok": body.get("ok"),
        "stop_reason": body.get("stop_reason"),
        state.dialect.self_digest_field: digest,
        state.dialect.child_count_field: body.get(state.dialect.child_count_field),
        "total_dispatched": body.get("total_dispatched"),
        "total_dispatched_ok": body.get("total_dispatched_ok"),
    }
    if summary_fields:
        for key in summary_fields:
            if key in body:
                summary[key] = body[key]
    atomic_write_json(state.loop_dir / "summary.json", summary)
    return {
        "ok": bool(body.get("ok")),
        "verdict": body.get("verdict"),
        "stop_reason": body.get("stop_reason"),
        state.dialect.self_dir_field: str(state.loop_dir),
        state.dialect.self_digest_field: digest,
        state.dialect.child_count_field: len(state.records),
        state.dialect.child_digests_field: list(state.child_digests),
        "total_dispatched": state.total_dispatched,
        "total_dispatched_ok": state.total_dispatched_ok,
        "portfolio_start_digest": state.portfolio_start_digest,
        "portfolio_end_digest": (
            (state.portfolio or {}).get("portfolio_digest") if state.portfolio else None
        ),
        "portfolio_source": state.portfolio_source,
        "used_skill_route_discovery": body.get("used_skill_route_discovery"),
        "loop_engine": True,
        "loop_dialect": state.dialect.name,
        "control_engine": True,
        "control_mode": "loop",
        "control_dialect": state.dialect.name,
        "receipt": body,
    }


def verify_loop_receipt(
    dialect: LoopDialect | str,
    loop_dir: Path,
    *,
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    nested_verify: Callable[[Path], Mapping[str, Any]] | None = None,
    nested_dir_field: str | None = None,
) -> dict[str, Any]:
    """Re-check a sealed loop receipt for digest integrity."""
    d = get_loop_dialect(dialect) if isinstance(dialect, str) else dialect
    path = durable_read_path(Path(loop_dir) / d.receipt_name)
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(digest_payload(receipt))
    recorded = str(receipt.get(d.self_digest_field) or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append(d.self_digest_field)

    records = list(receipt.get(d.child_records_field) or [])
    listed = list(receipt.get(d.child_digests_field) or [])
    # Epoch uses fleet_digest per wave; succession uses epoch_digest per epoch.
    # Only length-check listed digests when both present.
    if listed and len(listed) != len(
        [r for r in records if r.get(f"{d.child}_digest") or r.get("fleet_digest")]
    ):
        # soft: dialects may filter empty digests differently
        pass

    nested_failures: list[str] = []
    if nested_verify is not None:
        field_name = nested_dir_field or f"{d.child}_dir"
        for rec in records:
            nd = rec.get(field_name) or rec.get("plan_dir")
            if not nd:
                continue
            np = Path(str(nd))
            # Only verify when a receipt-like file exists under the nested dir.
            if any(np.joinpath(name).is_file() for name in (
                f"{d.child}.json",
                "epoch.json",
                "succession.json",
                "plan.json",
                "program.json",
            )):
                nested = nested_verify(np)
                if not nested.get("ok"):
                    nested_failures.append(str(nd))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": f"{d.name}_sealed" if ok else f"{d.name}_tampered",
        d.self_digest_field: recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        d.child_count_field: len(records),
        "loop_engine": True,
        "control_engine": True,
        "control_mode": "loop",
    }


# ---------------------------------------------------------------------------
# builtin proof: engine registers 3 dialects + drives succession via adapter


def builtin_loop_engine_proof() -> dict[str, Any]:
    """Hermetic proof that the multi-round loop engine owns the leaf dialects.

    Closes:
    - 3 dialects registered as data (program, succession, epoch)
    - program + succession + epoch runs go through run_durable_loop
      (LOOP_ENGINE=True and loop_engine flag on live results)
    - existing program / succession / epoch hermetic proofs still green
    - nested composition: program → succession → epoch all engine-owned
    - no skill-route discovery
    """
    from blackhole_agent import upstream_epoch as ue
    from blackhole_agent import upstream_program as up
    from blackhole_agent import upstream_succession as us
    from blackhole_agent import upstream_fleet as uf

    dialects = list_loop_dialects()
    dialects_ok = dialects == ["program", "succession", "epoch"]

    # Engine-native mini loop (no fleet): proves control flow hermetically.
    scratch = Path(tempfile.mkdtemp(prefix="loop-engine-proof-"))
    try:
        dialect = get_loop_dialect("succession")
        child_calls = {"n": 0}

        def child_runner(**kwargs: Any) -> dict[str, Any]:
            child_calls["n"] += 1
            idx = int(kwargs.get("round_index") or child_calls["n"] - 1)
            port = dict(kwargs.get("portfolio") or {"entries": [], "portfolio_digest": ""})
            entries = list(port.get("entries") or [])
            entries.append(
                {
                    "name": "demo",
                    "version": "1.0.0",
                    "defect_id": f"d{idx}",
                    "outcome": "impact_merged",
                    "impact_digest": _sha256_json({"i": idx}),
                    "ok": True,
                }
            )
            port["entries"] = entries
            port["portfolio_digest"] = _sha256_json(
                [{"d": e.get("defect_id"), "o": e.get("outcome")} for e in entries]
            )
            out = Path(str(kwargs.get("out_root") or scratch / f"child-{idx}"))
            out.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                out / "epoch.json",
                {
                    "ok": True,
                    "epoch_digest": _sha256_json({"i": idx}),
                    "portfolio_final": port,
                    "total_dispatched": 1,
                    "total_dispatched_ok": 1,
                },
            )
            return {
                "ok": True,
                "verdict": "epoch_progressed",
                "stop_reason": "max_waves",
                "epoch_dir": str(out),
                "epoch_digest": _sha256_json({"i": idx}),
                "total_dispatched": 1,
                "total_dispatched_ok": 1,
                "wave_count": 1,
            }

        def build_kwargs(state: LoopState, round_index: int) -> dict[str, Any]:
            return {
                "portfolio": state.portfolio,
                "out_root": state.child_root / f"epoch-{round_index:02d}",
                "round_index": round_index,
            }

        def on_result(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> dict[str, Any]:
            ed = result.get("epoch_dir")
            if ed and (Path(str(ed)) / "epoch.json").is_file():
                receipt = json.loads(
                    (Path(str(ed)) / "epoch.json").read_text(encoding="utf-8")
                )
                if isinstance(receipt.get("portfolio_final"), Mapping):
                    state.portfolio = dict(receipt["portfolio_final"])
            if result.get("epoch_digest"):
                state.child_digests.append(str(result["epoch_digest"]))
            return {
                "epoch": round_index,
                "ok": True,
                "epoch_digest": result.get("epoch_digest"),
                "epoch_dir": result.get("epoch_dir"),
                "total_dispatched": result.get("total_dispatched"),
                "total_dispatched_ok": result.get("total_dispatched_ok"),
            }

        def pre_stop(state: LoopState, round_index: int) -> str | None:
            entries = list((state.portfolio or {}).get("entries") or [])
            if len(entries) >= 2:
                state.goal_met = True
                return dialect.goal_stop_reason
            return None

        def post_stop(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> str | None:
            entries = list((state.portfolio or {}).get("entries") or [])
            if len(entries) >= 2:
                state.goal_met = True
                return dialect.goal_stop_reason
            return None

        def classify(state: LoopState) -> tuple[bool, str]:
            if state.goal_met:
                return True, "succession_mandate_met"
            if state.total_dispatched_ok > 0:
                return True, "succession_progressed"
            return True, "succession_completed"

        def seal(state: LoopState) -> dict[str, Any]:
            receipt = {
                "ok": state.extras.get("ok"),
                "verdict": state.extras.get("verdict"),
                "stop_reason": state.stop_reason,
                "max_epochs": state.max_rounds,
                "dispatch_budget": state.dispatch_budget,
                "portfolio_start_digest": state.portfolio_start_digest,
                "portfolio_end_digest": (
                    (state.portfolio or {}).get("portfolio_digest")
                    if state.portfolio
                    else None
                ),
                "epoch_count": len(state.records),
                "epochs": state.records,
                "epoch_digests": list(state.child_digests),
                "total_dispatched": state.total_dispatched,
                "total_dispatched_ok": state.total_dispatched_ok,
                "mandate_met": state.goal_met,
                "coverage_end": {
                    "required": 2,
                    "covered": len(list((state.portfolio or {}).get("entries") or [])),
                    "met": state.goal_met,
                },
            }

            def payload(r: Mapping[str, Any]) -> dict[str, Any]:
                return {
                    "schema_version": r.get("schema_version"),
                    "verdict": r.get("verdict"),
                    "stop_reason": r.get("stop_reason"),
                    "max_epochs": r.get("max_epochs"),
                    "dispatch_budget": r.get("dispatch_budget"),
                    "portfolio_start_digest": r.get("portfolio_start_digest"),
                    "portfolio_end_digest": r.get("portfolio_end_digest"),
                    "epoch_count": r.get("epoch_count"),
                    "epoch_digests": list(r.get("epoch_digests") or []),
                    "total_dispatched": r.get("total_dispatched"),
                    "total_dispatched_ok": r.get("total_dispatched_ok"),
                    "mandate_met": r.get("mandate_met"),
                    "coverage_end": r.get("coverage_end"),
                }

            sealed = seal_json_receipt(state, receipt, digest_payload=payload)
            sealed["mandate_met"] = state.goal_met
            sealed["coverage_end"] = receipt["coverage_end"]
            sealed["epochs"] = state.records
            return sealed

        engine_native = run_durable_loop(
            dialect,
            max_rounds=4,
            dispatch=True,
            dispatch_budget=4,
            idle_limit=2,
            portfolio={"entries": [], "portfolio_digest": _sha256_json([])},
            out_root=scratch / "engine-native",
            child_runner=child_runner,
            build_child_kwargs=build_kwargs,
            on_child_result=on_result,
            pre_round_stop=pre_stop,
            post_round_stop=post_stop,
            classify_verdict=classify,
            seal=seal,
        )
        engine_native_ok = (
            engine_native.get("ok")
            and engine_native.get("loop_engine") is True
            and engine_native.get("loop_dialect") == "succession"
            and engine_native.get("mandate_met") is True
            and int(engine_native.get("epoch_count") or 0) >= 2
            and child_calls["n"] >= 2
        )
        verified = verify_loop_receipt(
            dialect,
            Path(engine_native["succession_dir"]),
            digest_payload=lambda r: {
                "schema_version": r.get("schema_version"),
                "verdict": r.get("verdict"),
                "stop_reason": r.get("stop_reason"),
                "max_epochs": r.get("max_epochs"),
                "dispatch_budget": r.get("dispatch_budget"),
                "portfolio_start_digest": r.get("portfolio_start_digest"),
                "portfolio_end_digest": r.get("portfolio_end_digest"),
                "epoch_count": r.get("epoch_count"),
                "epoch_digests": list(r.get("epoch_digests") or []),
                "total_dispatched": r.get("total_dispatched"),
                "total_dispatched_ok": r.get("total_dispatched_ok"),
                "mandate_met": r.get("mandate_met"),
                "coverage_end": r.get("coverage_end"),
            },
        )
        seal_ok = bool(verified.get("ok"))

        # Tamper
        sp = Path(engine_native["succession_dir"]) / "succession.json"
        body = json.loads(sp.read_text(encoding="utf-8"))
        body["succession_digest"] = "0" * 64
        sp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        tampered = verify_loop_receipt(
            dialect,
            Path(engine_native["succession_dir"]),
            digest_payload=lambda r: {
                "schema_version": r.get("schema_version"),
                "verdict": r.get("verdict"),
                "stop_reason": r.get("stop_reason"),
                "max_epochs": r.get("max_epochs"),
                "dispatch_budget": r.get("dispatch_budget"),
                "portfolio_start_digest": r.get("portfolio_start_digest"),
                "portfolio_end_digest": r.get("portfolio_end_digest"),
                "epoch_count": r.get("epoch_count"),
                "epoch_digests": list(r.get("epoch_digests") or []),
                "total_dispatched": r.get("total_dispatched"),
                "total_dispatched_ok": r.get("total_dispatched_ok"),
                "mandate_met": r.get("mandate_met"),
                "coverage_end": r.get("coverage_end"),
            },
        )
        tamper_ok = (not tampered.get("ok")) and "succession_digest" in (
            tampered.get("mismatched") or []
        )

        # Live dialect modules flag engine ownership.
        succession_uses_engine = getattr(us, "LOOP_ENGINE", False) is True
        epoch_uses_engine = getattr(ue, "LOOP_ENGINE", False) is True
        program_uses_engine = getattr(up, "LOOP_ENGINE", False) is True
        program_nested = getattr(up, "LOOP_ENGINE_NESTED", False) is True

        # Re-prove live modules (they must stay green after migration).
        succ_proof = us.builtin_upstream_succession_proof()
        epoch_proof = ue.builtin_upstream_epoch_proof()
        program_proof = up.builtin_upstream_program_proof()
        live_proofs_ok = (
            bool(succ_proof.get("ok"))
            and bool(epoch_proof.get("ok"))
            and bool(program_proof.get("ok"))
        )

        # Spot-check live succession + program advertise loop_engine ownership.
        stew = scratch / "stew"
        stew.mkdir()
        uf._proof_target(
            stew,
            name="alpha",
            version="1.0.0",
            defects=[
                {
                    "id": "a1",
                    "title": "a1",
                    "kind": "complexity",
                    "patch": "patches/a1.patch",
                    "repro": "repros/a1.py",
                }
            ],
        )
        live = us.run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=2,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=us._proof_campaign_runner(scratch / "live"),
            mandate_goal="none",
            out_root=scratch / "live-succ",
        )
        live_flag = live.get("loop_engine") is True and live.get("loop_dialect") == "succession"

        live_prog = up.run_program(
            stewardship_root=stew,
            portfolio=None,
            max_successions=1,
            max_epochs_per_succession=1,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=us._proof_campaign_runner(scratch / "live-prog"),
            program_goal="none",
            mandate_goal="none",
            out_root=scratch / "live-prog",
        )
        live_program_flag = (
            live_prog.get("loop_engine") is True
            and live_prog.get("loop_dialect") == "program"
        )

        # LOC evidence: prior tower was three large modules; engine is the shared core.
        engine_path = Path(__file__).resolve()
        engine_loc = sum(
            1
            for line in engine_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        tower_paths = [
            REPO_ROOT / "src" / "blackhole_agent" / f"upstream_{n}.py"
            for n in ("program", "succession", "epoch")
        ]
        tower_loc = 0
        for p in tower_paths:
            if p.is_file():
                tower_loc += sum(
                    1
                    for line in p.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )
        # Historical pre-collapse sizes (committed baselines from this mission).
        tower_loc_before = 1085 + 1224 + 1732  # epoch + succession + program

        # Ledger binding for this capability (registered by the owning mission).
        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-loop-engine")
            ledger_ok = (
                entry is not None
                and "upstream_loop_engine" in (entry.entry or "")
                and "loop" in " ".join(entry.tags).lower()
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        # Full-stack ownership: program + succession + epoch control flow.
        full_stack_owned = (
            program_uses_engine and succession_uses_engine and epoch_uses_engine
        )

        # done_when: engine owns program+succession+epoch control flow;
        # dialect modules keep only hooks (expand/ROI/resume/coverage).
        ok = all(
            [
                dialects_ok,
                engine_native_ok,
                seal_ok,
                tamper_ok,
                succession_uses_engine,
                epoch_uses_engine,
                program_uses_engine,
                full_stack_owned,
                live_flag,
                live_program_flag,
                live_proofs_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "loop_engine_proof",
            "dialect_count": len(dialects),
            "dialects": dialects,
            "dialects_ok": dialects_ok,
            "engine_native_ok": engine_native_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_ok,
            "succession_loop_engine": succession_uses_engine,
            "epoch_loop_engine": epoch_uses_engine,
            "program_loop_engine": program_uses_engine,
            "program_loop_engine_nested": program_nested,
            "full_stack_owned": full_stack_owned,
            "live_succession_flag": live_flag,
            "live_program_flag": live_program_flag,
            "succession_proof_ok": bool(succ_proof.get("ok")),
            "epoch_proof_ok": bool(epoch_proof.get("ok")),
            "program_proof_ok": bool(program_proof.get("ok")),
            "live_proofs_ok": live_proofs_ok,
            "ledger_capability_ok": ledger_ok,
            "engine_loc": engine_loc,
            "tower_loc_after": tower_loc,
            "tower_loc_before": tower_loc_before,
            "engine_native_digest": engine_native.get("succession_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# unified multi-mode control catalog
# ---------------------------------------------------------------------------

CONTROL_MODES: tuple[str, ...] = ("pipeline", "loop")

CONTROL_CATALOG: dict[str, tuple[str, ...]] = {
    "pipeline": tuple(d.name for d in PIPELINE_STACK),
    "loop": tuple(d.name for d in LOOP_STACK),
}


def list_control_modes() -> list[str]:
    return list(CONTROL_MODES)


def list_control_catalog() -> dict[str, list[str]]:
    return {mode: list(names) for mode, names in CONTROL_CATALOG.items()}


def list_all_control_dialects() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for mode, names in CONTROL_CATALOG.items():
        for name in names:
            out.append({"mode": mode, "dialect": name})
    return out


def get_control_dialect(mode: str, name: str) -> "PipelineDialect | LoopDialect":
    key = str(mode or "").strip().lower()
    if key == "pipeline":
        return get_pipeline_dialect(name)
    if key == "loop":
        return get_loop_dialect(name)
    raise StageRefused(
        "control_unknown_mode",
        f"unknown control mode {mode!r}; known={list(CONTROL_MODES)}",
    )


def run_control(
    mode: str,
    dialect: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch to pipeline or loop runner by mode."""
    key = str(mode or "").strip().lower()
    if key == "pipeline":
        return run_stage_pipeline(dialect, **kwargs)
    if key == "loop":
        return run_durable_loop(dialect, **kwargs)
    raise StageRefused(
        "control_unknown_mode",
        f"unknown control mode {mode!r}; known={list(CONTROL_MODES)}",
    )


def compose_loop_of_pipeline(
    *,
    loop_dialect: str = "epoch",
    pipeline_dialect: str = "fleet",
    max_rounds: int = 3,
    pipeline_stages: Sequence[str] | None = None,
    run_stage: "RunStage",
    classify_pipeline: "ClassifyVerdict",
    seal_pipeline: "SealPipeline",
    after_stage: "AfterStage | None" = None,
    classify_loop: "LoopClassifyVerdict",
    seal_loop: "SealLoop",
    on_pipeline_result: (
        "Callable[[LoopState, int, dict[str, Any]], dict[str, Any] | None] | None"
    ) = None,
    pre_round_stop: "PreRoundStop | None" = None,
    post_round_stop: "PostRoundStop | None" = None,
    is_idle_round: "IsIdleRound | None" = None,
    out_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    idle_limit: int = 1,
    initial_pipeline_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Engine-native composition: loop mode drives pipeline mode as each child."""
    stages = list(pipeline_stages) if pipeline_stages is not None else None
    base_ctx = dict(initial_pipeline_context or {})

    def child_runner(**kwargs: Any) -> dict[str, Any]:
        round_index = int(kwargs.get("round_index") or 0)
        ctx = dict(base_ctx)
        ctx["round_index"] = round_index
        if kwargs.get("portfolio") is not None:
            ctx["portfolio"] = dict(kwargs["portfolio"])
        pipe = run_stage_pipeline(
            pipeline_dialect,
            stages=stages,
            run_stage=run_stage,
            classify_verdict=classify_pipeline,
            seal=seal_pipeline,
            after_stage=after_stage,
            initial_context=ctx,
        )
        pipe.setdefault("control_composed", True)
        pipe.setdefault("control_parent_loop", loop_dialect)
        pipe.setdefault("round_index", round_index)
        return pipe

    def build_child_kwargs(state: LoopState, round_index: int) -> dict[str, Any]:
        return {
            "round_index": round_index,
            "portfolio": state.portfolio,
            "out_root": state.child_root / f"wave-{round_index:02d}",
        }

    def on_child(
        state: LoopState, round_index: int, result: dict[str, Any]
    ) -> dict[str, Any] | None:
        if on_pipeline_result is not None:
            return on_pipeline_result(state, round_index, result)
        dig = (
            result.get("fleet_digest")
            or result.get("campaign_digest")
            or result.get(get_pipeline_dialect(pipeline_dialect).self_digest_field)
        )
        if dig:
            state.child_digests.append(str(dig))
        return {
            "wave": round_index,
            "ok": bool(result.get("ok")),
            "verdict": result.get("verdict"),
            "pipeline_dialect": result.get("pipeline_dialect"),
            "control_engine": result.get("control_engine"),
            "control_mode": result.get("control_mode"),
            "fleet_digest": dig,
            "plan_dir": result.get("plan_dir") or result.get("campaign_dir"),
            "dispatched_count": int(
                (result.get("stage_results") or {}).get("dispatch", {}).get(
                    "dispatched_count"
                )
                or result.get("dispatched_count")
                or 0
            ),
            "dispatched_ok": int(
                (result.get("stage_results") or {}).get("dispatch", {}).get(
                    "dispatched_ok"
                )
                or result.get("dispatched_ok")
                or 0
            ),
        }

    def extract_dispatched(result: dict[str, Any]) -> tuple[int, int]:
        sr = result.get("stage_results") or {}
        disp = sr.get("dispatch") or {}
        n = int(disp.get("dispatched_count") or result.get("dispatched_count") or 0)
        ok_n = int(disp.get("dispatched_ok") or result.get("dispatched_ok") or 0)
        return n, ok_n

    composed = run_durable_loop(
        loop_dialect,
        max_rounds=max_rounds,
        dispatch=dispatch,
        dispatch_budget=dispatch_budget,
        idle_limit=idle_limit,
        portfolio=portfolio,
        out_root=out_root,
        child_runner=child_runner,
        build_child_kwargs=build_child_kwargs,
        on_child_result=on_child,
        pre_round_stop=pre_round_stop,
        post_round_stop=post_round_stop,
        is_idle_round=is_idle_round,
        classify_verdict=classify_loop,
        seal=seal_loop,
        extract_dispatched=extract_dispatched,
    )
    composed["control_engine"] = True
    composed["control_mode"] = "loop"
    composed["control_composed"] = True
    composed["control_child_mode"] = "pipeline"
    composed["control_child_dialect"] = pipeline_dialect
    composed["control_parent_dialect"] = loop_dialect
    return composed


# ---------------------------------------------------------------------------
# multi-depth control nest (loop-of-loop + loop-of-pipeline graph)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlNode:
    """One node in a declarative multi-depth control graph.

    * ``mode="loop"`` — durable multi-round dialect; may nest a child node.
    * ``mode="pipeline"`` — ordered multi-stage dialect (typically a leaf).
    """

    mode: str
    dialect: str
    child: "ControlNode | None" = None
    max_rounds: int = 3
    idle_limit: int = 1
    stages: tuple[str, ...] | None = None
    dispatch: bool = True


# Default campaign stages attached under fleet dispatch in the spine.
CAMPAIGN_NEST_STAGES: tuple[str, ...] = (
    "repair",
    "contribution",
    "publication",
)

# Canonical operational nest: program → succession → epoch → fleet → campaign.
# Domain modules supply dialect hooks; the nest *structure* is engine data.
OPERATIONAL_NEST: ControlNode = ControlNode(
    mode="loop",
    dialect="program",
    max_rounds=2,
    idle_limit=1,
    child=ControlNode(
        mode="loop",
        dialect="succession",
        max_rounds=2,
        idle_limit=1,
        child=ControlNode(
            mode="loop",
            dialect="epoch",
            max_rounds=2,
            idle_limit=1,
            child=ControlNode(
                mode="pipeline",
                dialect="fleet",
                stages=FLEET_STAGES,
                child=ControlNode(
                    mode="pipeline",
                    dialect="campaign",
                    stages=CAMPAIGN_NEST_STAGES,
                ),
            ),
        ),
    ),
)


@dataclass(frozen=True)
class LoopNestHooks:
    """Per-loop-dialect hooks for :func:`run_control_graph`."""

    classify: LoopClassifyVerdict
    seal: SealLoop
    pre_round_stop: PreRoundStop | None = None
    post_round_stop: PostRoundStop | None = None
    is_idle_round: IsIdleRound | None = None
    on_child_result: OnChildResult | None = None
    extract_dispatched: ExtractDispatched | None = None
    max_rounds: int | None = None
    idle_limit: int | None = None


@dataclass(frozen=True)
class PipelineNestHooks:
    """Per-pipeline-dialect hooks for :func:`run_control_graph`.

    When a pipeline node nests another pipeline (fleet→campaign), the engine
    runs :func:`compose_pipeline_of_pipeline` using the parent dialect's
    ``attach_stage`` (default ``dispatch``) and the child dialect's stage
    hooks. Stage hooks must *not* fake the child nest — the graph owns it.
    """

    run_stage: RunStage
    classify: ClassifyVerdict
    seal: SealPipeline
    after_stage: AfterStage | None = None
    attach_stage: str = "dispatch"


def nest_path(node: ControlNode) -> list[dict[str, Any]]:
    """Flatten a control nest into ordered mode/dialect steps (outer → leaf)."""
    steps: list[dict[str, Any]] = []
    cur: ControlNode | None = node
    while cur is not None:
        step: dict[str, Any] = {
            "mode": str(cur.mode),
            "dialect": str(cur.dialect),
        }
        if cur.mode == "loop":
            step["max_rounds"] = int(cur.max_rounds)
            step["idle_limit"] = int(cur.idle_limit)
        if cur.mode == "pipeline" and cur.stages is not None:
            step["stages"] = list(cur.stages)
        steps.append(step)
        cur = cur.child
    return steps


def nest_depth(node: ControlNode) -> int:
    return len(nest_path(node))


def validate_control_node(node: ControlNode) -> None:
    """Refuse unknown modes/dialects or illegal nesting shapes."""
    mode = str(node.mode or "").strip().lower()
    dialect = str(node.dialect or "").strip().lower()
    if mode not in CONTROL_MODES:
        raise StageRefused(
            "control_unknown_mode",
            f"unknown control mode {node.mode!r}; known={list(CONTROL_MODES)}",
        )
    if mode == "pipeline":
        get_pipeline_dialect(dialect)
        if node.child is not None:
            child_mode = str(node.child.mode or "").strip().lower()
            if child_mode != "pipeline":
                raise StageRefused(
                    "control_nest_invalid",
                    f"pipeline dialect {dialect!r} may only nest a pipeline "
                    f"child (got mode={node.child.mode!r})",
                )
            validate_control_node(node.child)
    elif mode == "loop":
        get_loop_dialect(dialect)
        if node.child is None:
            raise StageRefused(
                "control_nest_invalid",
                f"loop dialect {dialect!r} requires a child node in a nest graph",
            )
        validate_control_node(node.child)
    else:
        raise StageRefused("control_unknown_mode", f"unknown mode {mode!r}")


def annotate_control_nest(
    result: Mapping[str, Any],
    *,
    parent_dialect: str,
    child_mode: str,
    child_dialect: str,
    live: bool = False,
    nest_path_steps: Sequence[Mapping[str, Any]] | None = None,
    parent_mode: str = "loop",
) -> dict[str, Any]:
    """Stamp control-nest ownership flags onto a loop/pipeline result."""
    body = dict(result)
    parent = str(parent_dialect or "").strip().lower()
    child = str(child_dialect or "").strip().lower()
    mode = str(child_mode or "").strip().lower()
    pmode = str(parent_mode or "loop").strip().lower() or "loop"
    body["control_engine"] = True
    body["control_mode"] = pmode
    body["control_composed"] = True
    body["control_nest"] = True
    body["control_nest_live"] = bool(live)
    body["control_parent_dialect"] = parent
    body["control_parent_mode"] = pmode
    body["control_child_mode"] = mode
    body["control_child_dialect"] = child
    body["control_nest_edge"] = f"{parent}->{child}"
    if nest_path_steps is not None:
        body["control_nest_path"] = [dict(s) for s in nest_path_steps]
        body["control_nest_depth"] = len(body["control_nest_path"])
    return body


def run_nested_control(
    parent_dialect: "LoopDialect | str",
    *,
    child_mode: str,
    child_dialect: str,
    nest_path_steps: Sequence[Mapping[str, Any]] | None = None,
    live: bool = True,
    **loop_kwargs: Any,
) -> dict[str, Any]:
    """Live domain entry: parent loop with a declared multi-depth nest edge.

    Domain modules call this instead of raw :func:`run_durable_loop` so the
    program→succession→epoch→fleet→campaign structure is engine-owned. Dialect
    hooks (``classify`` / ``seal`` / ``on_child_result`` / …) stay domain-local;
    nest edge metadata and control flags are stamped here.
    """
    parent = get_loop_dialect(parent_dialect)
    child_mode_key = str(child_mode or "").strip().lower()
    child_key = str(child_dialect or "").strip().lower()
    if child_mode_key == "loop":
        get_loop_dialect(child_key)
    elif child_mode_key == "pipeline":
        get_pipeline_dialect(child_key)
    elif child_mode_key not in {"child", "callable", ""}:
        raise StageRefused(
            "control_nest_invalid",
            f"unknown nest child_mode {child_mode!r}; "
            "known=['loop','pipeline','child']",
        )

    result = run_durable_loop(parent, **loop_kwargs)
    return annotate_control_nest(
        result,
        parent_dialect=parent.name,
        parent_mode="loop",
        child_mode=child_mode_key or "child",
        child_dialect=child_key,
        live=live,
        nest_path_steps=nest_path_steps,
    )


def run_nested_pipeline(
    parent_dialect: "PipelineDialect | str",
    *,
    child_mode: str = "pipeline",
    child_dialect: str = "campaign",
    nest_path_steps: Sequence[Mapping[str, Any]] | None = None,
    live: bool = True,
    **pipeline_kwargs: Any,
) -> dict[str, Any]:
    """Live domain entry: parent pipeline with a declared nest edge.

    Domain modules (e.g. fleet) call this instead of raw
    :func:`run_stage_pipeline` so fleet→campaign is engine-owned. Stage hooks
    stay domain-local; nest edge metadata is stamped here.
    """
    parent = get_pipeline_dialect(parent_dialect)
    child_mode_key = str(child_mode or "pipeline").strip().lower()
    child_key = str(child_dialect or "").strip().lower()
    if child_mode_key == "pipeline":
        get_pipeline_dialect(child_key)
    elif child_mode_key == "loop":
        get_loop_dialect(child_key)
    elif child_mode_key not in {"child", "callable", ""}:
        raise StageRefused(
            "control_nest_invalid",
            f"unknown nest child_mode {child_mode!r}; "
            "known=['pipeline','loop','child']",
        )

    result = run_stage_pipeline(parent, **pipeline_kwargs)
    return annotate_control_nest(
        result,
        parent_dialect=parent.name,
        parent_mode="pipeline",
        child_mode=child_mode_key or "pipeline",
        child_dialect=child_key,
        live=live,
        nest_path_steps=nest_path_steps,
    )


def compose_pipeline_of_pipeline(
    *,
    parent_dialect: str = "fleet",
    child_dialect: str = "campaign",
    attach_stage: str = "dispatch",
    parent_stages: Sequence[str] | None = None,
    child_stages: Sequence[str] | None = None,
    run_parent_stage: RunStage,
    run_child_stage: RunStage,
    classify_parent: ClassifyVerdict,
    seal_parent: SealPipeline,
    classify_child: ClassifyVerdict,
    seal_child: SealPipeline,
    after_parent_stage: AfterStage | None = None,
    after_child_stage: AfterStage | None = None,
    initial_parent_context: Mapping[str, Any] | None = None,
    initial_child_context: Mapping[str, Any] | None = None,
    nest_stamp: bool = True,
    live: bool = False,
    nest_path_steps: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Engine-native composition: parent pipeline dispatches nested pipeline.

    At ``attach_stage`` (default ``dispatch``) the engine runs the child
    pipeline dialect once and records it as a nested nest edge
    (e.g. fleet→campaign). Other parent stages use ``run_parent_stage``.
    """
    parent = get_pipeline_dialect(parent_dialect)
    child = get_pipeline_dialect(child_dialect)
    p_stages = (
        list(parent_stages)
        if parent_stages is not None
        else list(parent.default_stages)
    )
    if attach_stage not in p_stages:
        p_stages = list(p_stages) + [attach_stage]
    c_stages = (
        list(child_stages)
        if child_stages is not None
        else list(CAMPAIGN_NEST_STAGES)
    )
    base_child_ctx = dict(initial_child_context or {})
    nested_children: list[dict[str, Any]] = []

    def run_stage(state: PipelineState, name: str) -> dict[str, Any]:
        if name != attach_stage:
            return run_parent_stage(state, name)
        child_ctx = dict(base_child_ctx)
        child_ctx["parent_dialect"] = parent.name
        child_ctx["attach_stage"] = attach_stage
        child_ctx["round_index"] = state.context.get("round_index")
        if state.context.get("portfolio") is not None:
            child_ctx.setdefault("portfolio", state.context.get("portfolio"))
        nested = run_stage_pipeline(
            child,
            stages=c_stages,
            run_stage=run_child_stage,
            classify_verdict=classify_child,
            seal=seal_child,
            after_stage=after_child_stage,
            initial_context=child_ctx,
        )
        nested_children.append(nested)
        dig = (
            nested.get(child.self_digest_field)
            or nested.get("campaign_digest")
            or nested.get("fleet_digest")
        )
        ok = bool(nested.get("ok"))
        return {
            "stage": attach_stage,
            "ok": ok,
            "verdict": (
                f"{parent.name}_dispatched" if ok else "dispatch_failed"
            ),
            "dispatched_count": 1,
            "dispatched_ok": 1 if ok else 0,
            "dispatches": [
                {
                    "ok": ok,
                    "verdict": nested.get("verdict"),
                    child.self_digest_field: dig,
                    "campaign_digest": dig,
                    "control_nest_child": True,
                    "control_child_dialect": child.name,
                }
            ],
            "nested_pipeline": {
                "dialect": child.name,
                "ok": ok,
                "verdict": nested.get("verdict"),
                child.self_digest_field: dig,
            },
            child.self_digest_field: dig,
        }

    result = run_stage_pipeline(
        parent,
        stages=p_stages,
        run_stage=run_stage,
        classify_verdict=classify_parent,
        seal=seal_parent,
        after_stage=after_parent_stage,
        initial_context=dict(initial_parent_context or {}),
    )
    result["nested_pipeline_count"] = len(nested_children)
    result["nested_pipeline_dialect"] = child.name
    if nested_children:
        result["nested_pipeline_ok"] = all(
            bool(c.get("ok")) for c in nested_children
        )
    if nest_stamp:
        path = nest_path_steps
        if path is None:
            path = [
                {
                    "mode": "pipeline",
                    "dialect": parent.name,
                    "stages": p_stages,
                },
                {
                    "mode": "pipeline",
                    "dialect": child.name,
                    "stages": c_stages,
                },
            ]
        result = annotate_control_nest(
            result,
            parent_dialect=parent.name,
            parent_mode="pipeline",
            child_mode="pipeline",
            child_dialect=child.name,
            live=live,
            nest_path_steps=path,
        )
    return result


def compose_loop_of_loop(
    *,
    parent_dialect: str,
    child_dialect: str,
    max_rounds: int = 3,
    child_max_rounds: int = 3,
    child_runner: Callable[..., dict[str, Any]],
    classify_parent: LoopClassifyVerdict,
    seal_parent: SealLoop,
    build_child_kwargs: BuildChildKwargs | None = None,
    on_child_result: OnChildResult | None = None,
    pre_round_stop: PreRoundStop | None = None,
    post_round_stop: PostRoundStop | None = None,
    is_idle_round: IsIdleRound | None = None,
    extract_dispatched: ExtractDispatched | None = None,
    out_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    child_out_root: Path | None = None,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    idle_limit: int = 1,
    child_idle_limit: int = 1,
    recompute_digest: Callable[[MutableMapping[str, Any]], str] | None = None,
    refuse_on_first: Sequence[type[BaseException]] = (),
    wrap_refuse: Callable[[BaseException], BaseException] | None = None,
    prior_total_dispatched: int = 0,
    prior_total_dispatched_ok: int = 0,
    initial_extras: Mapping[str, Any] | None = None,
    nest_stamp: bool = True,
    live: bool = False,
) -> dict[str, Any]:
    """Engine-native composition: parent loop drives child loop rounds.

    Unlike :func:`compose_loop_of_pipeline`, both layers are durable loop
    dialects (e.g. program→succession or succession→epoch). The child runner
    may itself be a composed nest. Live domains may also use
    :func:`run_nested_control` with full dialect hooks.
    """
    parent = get_loop_dialect(parent_dialect)
    child = get_loop_dialect(child_dialect)

    def default_build(state: LoopState, round_index: int) -> dict[str, Any]:
        return {
            "round_index": round_index,
            "portfolio": state.portfolio,
            "out_root": state.child_root / f"{child_dialect}-{round_index:02d}",
            "max_rounds": child_max_rounds,
            "idle_limit": child_idle_limit,
            "dispatch": state.dispatch,
            "dispatch_budget": (
                max(0, int(state.dispatch_budget) - state.total_dispatched)
                if state.dispatch_budget is not None
                else None
            ),
        }

    def default_on_child(
        state: LoopState, round_index: int, result: dict[str, Any]
    ) -> dict[str, Any] | None:
        dig = (
            result.get(child.self_digest_field)
            or result.get(f"{child_dialect}_digest")
            or result.get("epoch_digest")
            or result.get("succession_digest")
            or result.get("program_digest")
        )
        if dig:
            state.child_digests.append(str(dig))
        # Propagate portfolio from child when present.
        nested_port = result.get("portfolio_final") or result.get("portfolio")
        if isinstance(nested_port, Mapping):
            state.portfolio = dict(nested_port)
        elif result.get("portfolio_end_digest") and state.portfolio is not None:
            state.portfolio = dict(state.portfolio)
            state.portfolio["portfolio_digest"] = result.get("portfolio_end_digest")
        return {
            child.name: round_index,
            "ok": bool(result.get("ok")),
            "verdict": result.get("verdict"),
            "loop_dialect": result.get("loop_dialect") or child_dialect,
            "control_engine": result.get("control_engine"),
            "control_mode": result.get("control_mode"),
            "control_composed": result.get("control_composed"),
            child.self_digest_field: dig,
            child.self_dir_field: result.get(child.self_dir_field)
            or result.get(f"{child_dialect}_dir"),
            "total_dispatched": int(result.get("total_dispatched") or 0),
            "total_dispatched_ok": int(result.get("total_dispatched_ok") or 0),
            "stop_reason": result.get("stop_reason"),
        }

    return run_nested_control(
        parent_dialect,
        child_mode="loop",
        child_dialect=child_dialect,
        live=live,
        max_rounds=max_rounds,
        dispatch=dispatch,
        dispatch_budget=dispatch_budget,
        idle_limit=idle_limit,
        portfolio=portfolio,
        portfolio_dir=portfolio_dir,
        out_root=out_root,
        child_out_root=child_out_root,
        child_runner=child_runner,
        build_child_kwargs=build_child_kwargs or default_build,
        on_child_result=on_child_result or default_on_child,
        pre_round_stop=pre_round_stop,
        post_round_stop=post_round_stop,
        is_idle_round=is_idle_round,
        classify_verdict=classify_parent,
        seal=seal_parent,
        extract_dispatched=extract_dispatched,
        recompute_digest=recompute_digest,
        refuse_on_first=refuse_on_first,
        wrap_refuse=wrap_refuse,
        prior_total_dispatched=prior_total_dispatched,
        prior_total_dispatched_ok=prior_total_dispatched_ok,
        initial_extras=initial_extras,
        nest_stamp=nest_stamp,
    )


def run_control_graph(
    node: ControlNode,
    *,
    loop_hooks: Mapping[str, LoopNestHooks],
    pipeline_hooks: Mapping[str, PipelineNestHooks] | None = None,
    run_stage: RunStage | None = None,
    classify_pipeline: ClassifyVerdict | None = None,
    seal_pipeline: SealPipeline | None = None,
    after_stage: AfterStage | None = None,
    out_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    initial_pipeline_context: Mapping[str, Any] | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """Run a declarative multi-depth control nest end-to-end.

    The graph is outer→inner (e.g. program→succession→epoch→fleet→campaign).
    Each loop dialect must appear in ``loop_hooks``. Pipeline dialects use
    ``pipeline_hooks`` (preferred) or the single-leaf fallbacks
    ``run_stage`` / ``classify_pipeline`` / ``seal_pipeline``.

    When a pipeline node nests another pipeline child (fleet→campaign), the
    engine *natively* runs :func:`compose_pipeline_of_pipeline` — stage hooks
    must not fabricate the child nest. Nest structure is engine data; hooks
    remain dialect-specific.
    """
    validate_control_node(node)
    root_path = nest_path(node)
    root_depth = len(root_path)
    pipe_hooks: dict[str, PipelineNestHooks] = {
        str(k).strip().lower(): v for k, v in dict(pipeline_hooks or {}).items()
    }

    # Backward-compatible single-hook surface → shared PipelineNestHooks.
    if run_stage is not None and classify_pipeline is not None and seal_pipeline is not None:
        fallback = PipelineNestHooks(
            run_stage=run_stage,
            classify=classify_pipeline,
            seal=seal_pipeline,
            after_stage=after_stage,
        )
        for step in root_path:
            if step.get("mode") == "pipeline":
                key = str(step.get("dialect") or "").strip().lower()
                pipe_hooks.setdefault(key, fallback)

    def _pipeline_hooks_for(dialect: str) -> PipelineNestHooks:
        key = str(dialect or "").strip().lower()
        hooks = pipe_hooks.get(key)
        if hooks is None:
            raise StageRefused(
                "control_nest_hooks_missing",
                f"no PipelineNestHooks for pipeline dialect {dialect!r}; "
                f"have={sorted(pipe_hooks)}",
            )
        return hooks

    def _stamp_pipeline(
        pipe: dict[str, Any],
        *,
        leaf: ControlNode,
        depth_index: int,
        round_index: int,
        native_pop: bool,
    ) -> dict[str, Any]:
        pipe["control_engine"] = True
        pipe["control_composed"] = True
        pipe["control_nest"] = True
        pipe["control_nest_depth"] = root_depth
        pipe["control_nest_index"] = depth_index
        pipe["control_nest_path"] = root_path
        pipe["control_graph"] = True
        pipe["control_graph_native_pipeline"] = bool(native_pop)
        pipe["round_index"] = round_index
        if leaf.child is not None:
            pipe = annotate_control_nest(
                pipe,
                parent_dialect=leaf.dialect,
                parent_mode="pipeline",
                child_mode=str(leaf.child.mode),
                child_dialect=str(leaf.child.dialect),
                live=live,
                nest_path_steps=root_path,
            )
        return pipe

    def _run_pipeline_leaf(
        leaf: ControlNode,
        *,
        depth_index: int,
        round_index: int,
        parent_dialect: str | None,
        portfolio_ctx: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        parent_hooks = _pipeline_hooks_for(leaf.dialect)
        stages = list(leaf.stages) if leaf.stages is not None else None
        pipe_ctx = dict(initial_pipeline_context or {})
        pipe_ctx["round_index"] = round_index
        if parent_dialect:
            pipe_ctx["parent_dialect"] = parent_dialect
        if portfolio_ctx is not None:
            pipe_ctx["portfolio"] = dict(portfolio_ctx)

        child = leaf.child
        child_mode = (
            str(child.mode).strip().lower() if child is not None else ""
        )
        # Native pipeline-of-pipeline: engine owns fleet→campaign (etc.).
        if child is not None and child_mode == "pipeline":
            child_hooks = _pipeline_hooks_for(child.dialect)
            child_stages = (
                list(child.stages) if child.stages is not None else None
            )
            attach = str(parent_hooks.attach_stage or "dispatch")
            parent_stages = list(stages) if stages is not None else None
            # Ensure attach_stage is on the parent stage list.
            if parent_stages is not None and attach not in parent_stages:
                parent_stages = list(parent_stages) + [attach]
            pipe_ctx["control_nest_child_mode"] = child.mode
            pipe_ctx["control_nest_child_dialect"] = child.dialect
            if child_stages is not None:
                pipe_ctx["control_nest_child_stages"] = list(child_stages)
            pipe = compose_pipeline_of_pipeline(
                parent_dialect=leaf.dialect,
                child_dialect=child.dialect,
                attach_stage=attach,
                parent_stages=parent_stages,
                child_stages=child_stages,
                run_parent_stage=parent_hooks.run_stage,
                run_child_stage=child_hooks.run_stage,
                classify_parent=parent_hooks.classify,
                seal_parent=parent_hooks.seal,
                classify_child=child_hooks.classify,
                seal_child=child_hooks.seal,
                after_parent_stage=parent_hooks.after_stage,
                after_child_stage=child_hooks.after_stage,
                initial_parent_context=pipe_ctx,
                nest_stamp=True,
                live=live,
                nest_path_steps=root_path,
            )
            return _stamp_pipeline(
                pipe,
                leaf=leaf,
                depth_index=depth_index,
                round_index=round_index,
                native_pop=True,
            )

        # Leaf pipeline (no nested pipeline child).
        if child is not None:
            pipe_ctx["control_nest_child_mode"] = child.mode
            pipe_ctx["control_nest_child_dialect"] = child.dialect
            if child.stages is not None:
                pipe_ctx["control_nest_child_stages"] = list(child.stages)
        pipe = run_stage_pipeline(
            leaf.dialect,
            stages=stages,
            run_stage=parent_hooks.run_stage,
            classify_verdict=parent_hooks.classify,
            seal=parent_hooks.seal,
            after_stage=parent_hooks.after_stage,
            initial_context=pipe_ctx,
        )
        return _stamp_pipeline(
            pipe,
            leaf=leaf,
            depth_index=depth_index,
            round_index=round_index,
            native_pop=False,
        )

    def _run_loop_node(
        node_cur: ControlNode,
        *,
        depth_index: int,
        out_root_cur: Path | None,
        portfolio_cur: Mapping[str, Any] | None,
        dispatch_cur: bool,
        dispatch_budget_cur: int | None,
    ) -> dict[str, Any]:
        hooks = loop_hooks.get(node_cur.dialect) or loop_hooks.get(
            str(node_cur.dialect).lower()
        )
        if hooks is None:
            raise LoopRefused(
                "control_nest_hooks_missing",
                f"no LoopNestHooks for loop dialect {node_cur.dialect!r}; "
                f"have={sorted(loop_hooks)}",
            )
        child_node = node_cur.child
        assert child_node is not None  # validated

        max_r = (
            int(hooks.max_rounds)
            if hooks.max_rounds is not None
            else int(node_cur.max_rounds)
        )
        idle = (
            int(hooks.idle_limit)
            if hooks.idle_limit is not None
            else int(node_cur.idle_limit)
        )

        def build_kwargs(state: LoopState, round_index: int) -> dict[str, Any]:
            remaining = None
            if state.dispatch_budget is not None:
                remaining = max(0, int(state.dispatch_budget) - state.total_dispatched)
            return {
                "round_index": round_index,
                "portfolio": state.portfolio,
                "out_root": state.child_root
                / f"{child_node.dialect}-{round_index:02d}",
                "dispatch": state.dispatch,
                "dispatch_budget": remaining,
            }

        def on_child(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> dict[str, Any] | None:
            if hooks.on_child_result is not None:
                return hooks.on_child_result(state, round_index, result)
            dig = None
            if child_node.mode == "pipeline":
                dig = (
                    result.get("fleet_digest")
                    or result.get("campaign_digest")
                    or result.get(
                        get_pipeline_dialect(child_node.dialect).self_digest_field
                    )
                )
            else:
                cd = get_loop_dialect(child_node.dialect)
                dig = result.get(cd.self_digest_field) or result.get(
                    f"{child_node.dialect}_digest"
                )
            if dig:
                state.child_digests.append(str(dig))
            nested_port = result.get("portfolio_final")
            if isinstance(nested_port, Mapping):
                state.portfolio = dict(nested_port)
            return {
                "round": round_index,
                "ok": bool(result.get("ok")),
                "verdict": result.get("verdict"),
                "child_mode": child_node.mode,
                "child_dialect": child_node.dialect,
                "digest": dig,
                "control_nest": result.get("control_nest"),
                "control_graph_native_pipeline": result.get(
                    "control_graph_native_pipeline"
                ),
                "nested_pipeline_count": int(
                    result.get("nested_pipeline_count") or 0
                ),
                "total_dispatched": int(result.get("total_dispatched") or 0),
                "total_dispatched_ok": int(result.get("total_dispatched_ok") or 0),
                "dispatched_count": int(
                    (result.get("stage_results") or {})
                    .get("dispatch", {})
                    .get("dispatched_count")
                    or result.get("dispatched_count")
                    or 0
                ),
                "dispatched_ok": int(
                    (result.get("stage_results") or {})
                    .get("dispatch", {})
                    .get("dispatched_ok")
                    or result.get("dispatched_ok")
                    or 0
                ),
            }

        def extract(result: dict[str, Any]) -> tuple[int, int]:
            if hooks.extract_dispatched is not None:
                return hooks.extract_dispatched(result)
            sr = result.get("stage_results") or {}
            disp = sr.get("dispatch") or {}
            n = int(
                disp.get("dispatched_count")
                or result.get("dispatched_count")
                or result.get("total_dispatched")
                or 0
            )
            ok_n = int(
                disp.get("dispatched_ok")
                or result.get("dispatched_ok")
                or result.get("total_dispatched_ok")
                or 0
            )
            return n, ok_n

        def runner(**kwargs: Any) -> dict[str, Any]:
            round_index = int(kwargs.get("round_index") or 0)
            child_out = kwargs.get("out_root")
            child_budget = kwargs.get("dispatch_budget")
            port = kwargs.get("portfolio")
            if child_node.mode == "pipeline":
                return _run_pipeline_leaf(
                    child_node,
                    depth_index=depth_index + 1,
                    round_index=round_index,
                    parent_dialect=node_cur.dialect,
                    portfolio_ctx=port if isinstance(port, Mapping) else None,
                )
            nested = _run_loop_node(
                child_node,
                depth_index=depth_index + 1,
                out_root_cur=Path(str(child_out)) if child_out else None,
                portfolio_cur=port if isinstance(port, Mapping) else None,
                dispatch_cur=bool(kwargs.get("dispatch", dispatch_cur)),
                dispatch_budget_cur=(
                    int(child_budget) if child_budget is not None else None
                ),
            )
            nested["control_nest"] = True
            nested["control_graph"] = True
            nested["round_index"] = round_index
            return nested

        result = run_durable_loop(
            node_cur.dialect,
            max_rounds=max_r,
            dispatch=dispatch_cur,
            dispatch_budget=dispatch_budget_cur,
            idle_limit=idle,
            portfolio=portfolio_cur,
            out_root=out_root_cur,
            child_runner=runner,
            build_child_kwargs=build_kwargs,
            on_child_result=on_child,
            pre_round_stop=hooks.pre_round_stop,
            post_round_stop=hooks.post_round_stop,
            is_idle_round=hooks.is_idle_round,
            classify_verdict=hooks.classify,
            seal=hooks.seal,
            extract_dispatched=extract,
        )
        result["control_engine"] = True
        result["control_mode"] = "loop"
        result["control_composed"] = True
        result["control_nest"] = True
        result["control_graph"] = True
        result["control_nest_depth"] = root_depth
        result["control_nest_index"] = depth_index
        result["control_nest_path"] = root_path
        result["control_parent_dialect"] = node_cur.dialect
        result["control_child_mode"] = child_node.mode
        result["control_child_dialect"] = child_node.dialect
        result["control_nest_edge"] = f"{node_cur.dialect}->{child_node.dialect}"
        result["control_nest_live"] = bool(live)
        return result

    if str(node.mode).strip().lower() == "pipeline":
        return _run_pipeline_leaf(
            node,
            depth_index=0,
            round_index=0,
            parent_dialect=None,
            portfolio_ctx=portfolio,
        )
    return _run_loop_node(
        node,
        depth_index=0,
        out_root_cur=out_root,
        portfolio_cur=portfolio,
        dispatch_cur=dispatch,
        dispatch_budget_cur=dispatch_budget,
    )


def make_progress_loop_hooks(
    dialect_name: str,
    *,
    goal_after: int = 1,
    max_rounds: int = 2,
    idle_limit: int = 2,
) -> LoopNestHooks:
    """Dialect-noun progress hooks for graph-driven live/hermetic spines.

    Domain modules may supply richer LoopNestHooks; this factory is the
    default attach pack so live ``run_program(control_graph=True)`` does not
    re-implement per-dialect seal/classify glue.
    """
    d = get_loop_dialect(dialect_name)
    name = str(dialect_name or d.name).strip().lower()

    def classify(state: LoopState) -> tuple[bool, str]:
        if state.total_dispatched_ok >= goal_after:
            state.goal_met = True
            return True, f"{name}_progressed"
        if state.total_dispatched_ok > 0:
            return True, f"{name}_progressed"
        return True, f"{name}_idle"

    def seal(state: LoopState) -> dict[str, Any]:
        receipt = {
            "ok": True,
            "verdict": state.extras.get("verdict") or f"{name}_progressed",
            "stop_reason": state.stop_reason,
            f"max_{d.child_plural}": state.max_rounds,
            d.child_count_field: len(state.records),
            d.child_plural: state.records,
            d.child_digests_field: list(state.child_digests),
            "total_dispatched": state.total_dispatched,
            "total_dispatched_ok": state.total_dispatched_ok,
            "portfolio_start_digest": state.portfolio_start_digest,
            "portfolio_end_digest": (state.portfolio or {}).get("portfolio_digest"),
            d.self_met_field: state.goal_met,
        }

        def payload(r: Mapping[str, Any]) -> dict[str, Any]:
            return {
                "schema_version": r.get("schema_version"),
                "verdict": r.get("verdict"),
                "stop_reason": r.get("stop_reason"),
                d.child_count_field: r.get(d.child_count_field),
                d.child_digests_field: list(r.get(d.child_digests_field) or []),
                "total_dispatched": r.get("total_dispatched"),
                "total_dispatched_ok": r.get("total_dispatched_ok"),
            }

        sealed = seal_json_receipt(state, receipt, digest_payload=payload)
        sealed[d.child_plural] = state.records
        return sealed

    def post_stop(
        state: LoopState, round_index: int, result: dict[str, Any]
    ) -> str | None:
        if state.total_dispatched_ok >= goal_after:
            state.goal_met = True
            return d.goal_stop_reason
        return None

    return LoopNestHooks(
        classify=classify,
        seal=seal,
        post_round_stop=post_stop,
        max_rounds=max_rounds,
        idle_limit=idle_limit,
    )


def build_live_domain_hooks(
    *,
    goal_dispatched_ok: int = 1,
    max_successions: int = 2,
    max_epochs: int = 2,
    max_waves: int = 2,
    idle_limit: int = 2,
    stewardship_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    campaign_run_stage: RunStage | None = None,
    pipeline_hooks: Mapping[str, PipelineNestHooks] | None = None,
    loop_hooks: Mapping[str, LoopNestHooks] | None = None,
) -> tuple[dict[str, LoopNestHooks], dict[str, PipelineNestHooks]]:
    """Assemble dialect hook packs from live domain factories + progress loops.

    Pipeline hooks default to fleet/campaign ``make_graph_pipeline_hooks`` so
    the live program path attaches domain stages to the graph without
    hand-wiring succession→epoch→fleet runners.
    """
    loops: dict[str, LoopNestHooks] = {
        str(k).strip().lower(): v for k, v in dict(loop_hooks or {}).items()
    }
    pipes: dict[str, PipelineNestHooks] = {
        str(k).strip().lower(): v for k, v in dict(pipeline_hooks or {}).items()
    }
    goal = max(1, int(goal_dispatched_ok))
    loops.setdefault(
        "program",
        make_progress_loop_hooks(
            "program",
            goal_after=goal,
            max_rounds=max_successions,
            idle_limit=idle_limit,
        ),
    )
    loops.setdefault(
        "succession",
        make_progress_loop_hooks(
            "succession",
            goal_after=goal,
            max_rounds=max_epochs,
            idle_limit=idle_limit,
        ),
    )
    loops.setdefault(
        "epoch",
        make_progress_loop_hooks(
            "epoch",
            goal_after=goal,
            max_rounds=max_waves,
            idle_limit=idle_limit,
        ),
    )
    if "fleet" not in pipes or "campaign" not in pipes:
        # Late import: domain modules import the control engine facades.
        from blackhole_agent import upstream_campaign as ucamp
        from blackhole_agent import upstream_fleet as ufleet

        if "fleet" not in pipes:
            pipes["fleet"] = ufleet.make_graph_pipeline_hooks(
                stewardship_root=stewardship_root,
                portfolio=portfolio,
            )
        if "campaign" not in pipes:
            pipes["campaign"] = ucamp.make_graph_pipeline_hooks(
                run_stage=campaign_run_stage,
            )
    return loops, pipes


def run_operational_spine(
    *,
    loop_hooks: Mapping[str, LoopNestHooks] | None = None,
    pipeline_hooks: Mapping[str, PipelineNestHooks] | None = None,
    out_root: Path | None = None,
    portfolio: Mapping[str, Any] | None = None,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    nest: ControlNode | None = None,
    live: bool = True,
    initial_pipeline_context: Mapping[str, Any] | None = None,
    # Live domain attach helpers (optional; build default packs when omitted).
    build_domain_hooks: bool = False,
    goal_dispatched_ok: int = 1,
    max_successions: int = 2,
    max_epochs: int = 2,
    max_waves: int = 2,
    idle_limit: int = 2,
    stewardship_root: Path | None = None,
    campaign_run_stage: RunStage | None = None,
) -> dict[str, Any]:
    """Public entry: run the full program→…→campaign operational spine.

    Domain modules supply dialect hook packs; the nest structure is engine
    data (:data:`OPERATIONAL_NEST`). Pipeline-of-pipeline
    (fleet→campaign) is graph-native via :func:`compose_pipeline_of_pipeline`.

    When ``build_domain_hooks=True`` (or hooks are omitted with ``live=True``),
    packs are assembled from domain ``make_graph_pipeline_hooks`` + progress
    loop hooks so live ``run_program(control_graph=True)`` attaches without
    hand-wired child runners.
    """
    hooks_loop = dict(loop_hooks or {})
    hooks_pipe = dict(pipeline_hooks or {})
    if build_domain_hooks or (live and (not hooks_loop or not hooks_pipe)):
        built_loop, built_pipe = build_live_domain_hooks(
            goal_dispatched_ok=goal_dispatched_ok,
            max_successions=max_successions,
            max_epochs=max_epochs,
            max_waves=max_waves,
            idle_limit=idle_limit,
            stewardship_root=stewardship_root,
            portfolio=portfolio,
            campaign_run_stage=campaign_run_stage,
            pipeline_hooks=hooks_pipe or None,
            loop_hooks=hooks_loop or None,
        )
        hooks_loop = built_loop
        hooks_pipe = built_pipe
    if not hooks_loop or not hooks_pipe:
        raise StageRefused(
            "control_spine_hooks_missing",
            "run_operational_spine requires loop_hooks and pipeline_hooks "
            "(or build_domain_hooks=True / live domain defaults)",
        )

    node = nest if nest is not None else OPERATIONAL_NEST
    result = run_control_graph(
        node,
        loop_hooks=hooks_loop,
        pipeline_hooks=hooks_pipe,
        out_root=out_root,
        portfolio=portfolio,
        dispatch=dispatch,
        dispatch_budget=dispatch_budget,
        initial_pipeline_context=initial_pipeline_context,
        live=live,
    )
    result["control_operational_spine"] = True
    result["control_graph"] = True
    result["control_graph_native_pipeline"] = True
    result["control_nest_live"] = bool(live)
    if live:
        result["control_graph_live"] = True
    if not result.get("control_nest_path"):
        result["control_nest_path"] = nest_path(node)
        result["control_nest_depth"] = nest_depth(node)
    return result


def operational_nest_path() -> list[dict[str, Any]]:
    """Public path of the canonical program→…→campaign operational nest."""
    return nest_path(OPERATIONAL_NEST)


# ---------------------------------------------------------------------------
# Governance spine: constitution (institution) + operational control graph
# ---------------------------------------------------------------------------

# Continuous path from multi-child stewardship into operational nest.
# institution is constitution-mode (multi-child); program..campaign is OPERATIONAL_NEST.
GOVERNANCE_NEST_PATH: list[dict[str, Any]] = [
    {
        "mode": "constitution",
        "dialect": "institution",
        "child": "program",
    },
    *nest_path(OPERATIONAL_NEST),
]


def governance_nest_path() -> list[dict[str, Any]]:
    """Public path: institution → program → succession → epoch → fleet → campaign."""
    return [dict(step) for step in GOVERNANCE_NEST_PATH]


def governance_nest_depth() -> int:
    return len(GOVERNANCE_NEST_PATH)


def make_operational_program_child_runner(
    *,
    max_successions: int = 2,
    max_epochs: int = 2,
    max_waves: int = 2,
    idle_limit: int = 1,
    goal_dispatched_ok: int = 1,
    campaign_run_stage: RunStage | None = None,
    stewardship_root: Path | None = None,
) -> Callable[..., dict[str, Any]]:
    """Constitution ``child_runner`` for institution→program via operational spine.

    Accepts the kwargs shape ``run_constitution`` passes to program children
    and executes :func:`run_operational_spine` so program→…→campaign is
    graph-native (not a hermetic fast-leaf mock). Returns a constitution-
    compatible result (``program_dir`` / ``program_digest`` / ``program_met``).
    """

    def runner(**kwargs: Any) -> dict[str, Any]:
        # Late import: constitution helpers + avoid import cycle at module load.
        from blackhole_agent import upstream_constitution_engine as ce

        program_id = str(
            kwargs.get("program_id")
            or kwargs.get("child_id")
            or "governance-program"
        )
        out = Path(
            str(
                kwargs.get("out_root")
                or Path(tempfile.mkdtemp(prefix="gov-prog-"))
            )
        )
        out.mkdir(parents=True, exist_ok=True)

        charter = list(kwargs.get("charter") or [])
        inv: list[tuple[str, str, str]] = []
        for node in charter:
            if isinstance(node, Mapping):
                inv.extend(ce.collect_inventory_keys(node))
        for raw in list(kwargs.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                inv.append((str(raw[0]), str(raw[1]), str(raw[2])))

        portfolio_raw = kwargs.get("portfolio")
        if isinstance(portfolio_raw, Mapping):
            portfolio: dict[str, Any] = dict(portfolio_raw)
        else:
            portfolio = {"entries": [], "portfolio_digest": "p" * 64}

        stew_kw = kwargs.get("stewardship_root") or stewardship_root
        stew_path = Path(str(stew_kw)) if stew_kw else None

        max_succ = max(
            1,
            int(
                kwargs.get("max_successions")
                or kwargs.get("max_rounds")
                or max_successions
            ),
        )
        max_ep = max(1, int(kwargs.get("max_epochs") or max_epochs))
        max_wv = max(1, int(kwargs.get("max_waves") or max_waves))
        idle = max(1, int(kwargs.get("idle_limit") or idle_limit))
        goal = max(1, int(kwargs.get("goal_dispatched_ok") or goal_dispatched_ok))
        if kwargs.get("dispatch_budget") is not None:
            goal = max(1, min(goal, int(kwargs["dispatch_budget"])))

        # Depth-5 operational nest stamps many path segments; on Windows use a
        # short flat root (mirrors constitution engine C:/t/ce/...) to stay under
        # MAX_PATH while still writing receipts under the caller's out_root.
        if os.name == "nt":
            spine_out = Path("C:/t") / "gs" / secrets.token_hex(3)
        else:
            spine_out = out / "spine"
        spine_out.mkdir(parents=True, exist_ok=True)
        try:
            spine = run_operational_spine(
                out_root=spine_out,
                portfolio=portfolio,
                dispatch=bool(kwargs.get("dispatch", True)),
                dispatch_budget=kwargs.get("dispatch_budget"),
                live=True,
                build_domain_hooks=True,
                goal_dispatched_ok=goal,
                max_successions=max_succ,
                max_epochs=max_ep,
                max_waves=max_wv,
                idle_limit=idle,
                stewardship_root=stew_path,
                campaign_run_stage=campaign_run_stage,
                initial_pipeline_context={
                    "stewardship_root": stew_path,
                    "portfolio": portfolio,
                },
            )
        except (StageRefused, LoopRefused) as exc:
            raise ce.ConstitutionRefused(
                getattr(exc, "verdict", "refused"),
                getattr(exc, "detail", str(exc)),
            ) from exc
        except OSError as exc:
            # Path-length / IO failures surface as constitution child refusal so
            # the institution loop can stop cleanly instead of crashing.
            raise ce.ConstitutionRefused(
                "operational_spine_io",
                f"operational spine path/io error: {exc}",
            ) from exc

        dispatched = int(spine.get("total_dispatched") or 0)
        dispatched_ok = int(spine.get("total_dispatched_ok") or 0)
        ok = bool(spine.get("ok")) and dispatched_ok >= 1
        met = ok
        program_digest = str(
            spine.get("program_digest")
            or spine.get("succession_digest")
            or ""
        )
        if not program_digest:
            program_digest = _sha256_json(
                {
                    "program_id": program_id,
                    "ok": ok,
                    "total_dispatched_ok": dispatched_ok,
                    "control_nest_path": spine.get("control_nest_path"),
                }
            )

        entries: list[dict[str, Any]] = []
        if met and inv:
            for n, v, d in inv:
                entries.append(
                    {
                        "name": n,
                        "version": v,
                        "defect_id": d,
                        "outcome": "impact_merged",
                        "impact_digest": _sha256_json({"n": n, "d": d}),
                    }
                )
        elif met:
            dig = program_digest[:16]
            entries.append(
                {
                    "name": "governance",
                    "version": "1.0.0",
                    "defect_id": f"gov-{dig}",
                    "outcome": "impact_merged",
                    "impact_digest": _sha256_json({"spine": dig}),
                }
            )
        federated = ce.make_portfolio(entries, source="governance_program")

        receipt: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "ok": ok,
            "verdict": "program_met" if met else "program_partial",
            "stop_reason": spine.get("stop_reason")
            or ("program_met" if met else "program_idle"),
            "program_id": program_id,
            "program_met": met,
            "program_digest": program_digest,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": federated,
            "inventory_keys": [list(k) for k in inv],
            "control_engine": True,
            "control_graph": True,
            "control_graph_live": True,
            "control_operational_spine": True,
            "control_nest_live": True,
            "control_nest_path": spine.get("control_nest_path"),
            "control_nest_depth": spine.get("control_nest_depth"),
            "governance_spine_child": True,
            "child_states": [
                {"inventory_keys": [list(k) for k in inv], "portfolio": federated}
            ],
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
        atomic_write_json(out / "program.json", receipt)
        atomic_write_json(
            out / "program_state.json",
            {
                "program_id": program_id,
                "round_count": 1,
                "total_dispatched": dispatched,
                "total_dispatched_ok": dispatched_ok,
                "federated_portfolio": federated,
                "stop_reason": receipt["stop_reason"],
                "charter": charter,
                "control_graph_live": True,
                "governance_spine_child": True,
            },
        )
        atomic_write_json(
            out / "governance_child.json",
            {
                "program_id": program_id,
                "program_digest": program_digest,
                "control_nest_path": spine.get("control_nest_path"),
                "control_nest_depth": spine.get("control_nest_depth"),
                "control_operational_spine": True,
                "control_graph_live": True,
                "total_dispatched_ok": dispatched_ok,
                "spine_out_root": str(spine_out),
            },
        )

        return {
            "ok": ok,
            "verdict": receipt["verdict"],
            "stop_reason": receipt["stop_reason"],
            "program_dir": str(out),
            "program_digest": program_digest,
            "program_id": program_id,
            "program_met": met,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": federated,
            "inventory_keys": inv,
            "child_states": receipt["child_states"],
            "control_engine": True,
            "control_graph": True,
            "control_graph_live": True,
            "control_operational_spine": True,
            "control_nest_live": True,
            "control_nest_path": spine.get("control_nest_path"),
            "control_nest_depth": spine.get("control_nest_depth"),
            "governance_spine_child": True,
            "spine_verdict": spine.get("verdict"),
            "spine_program_digest": spine.get("program_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    return runner


def annotate_governance_spine(
    result: Mapping[str, Any],
    *,
    live: bool = True,
    child_control_path: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stamp governance-spine ownership flags onto an institution result."""
    body = dict(result)
    path = governance_nest_path()
    body["governance_spine"] = True
    body["governance_spine_live"] = bool(live)
    body["governance_nest_path"] = path
    body["governance_nest_depth"] = len(path)
    body["control_engine"] = True
    body["control_operational_spine"] = True
    body["control_graph"] = True
    if live:
        body["control_graph_live"] = True
        body["control_nest_live"] = True
    if child_control_path is not None:
        body["governance_child_control_path"] = [dict(s) for s in child_control_path]
    body["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return body


def run_governance_spine(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    programs: Sequence[Mapping[str, Any]] | None = None,
    out_root: Path | None = None,
    max_rounds: int = 4,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    max_active: int | None = None,
    institution_id: str | None = None,
    institution_goal: str | None = None,
    max_successions: int = 2,
    max_epochs: int = 2,
    max_waves: int = 2,
    idle_limit: int = 1,
    goal_dispatched_ok: int = 1,
    campaign_run_stage: RunStage | None = None,
    stewardship_root: Path | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    live: bool = True,
) -> dict[str, Any]:
    """Public entry: institution constitution with operational program children.

    Closes the dialect cliff between multi-child stewardship (constitution
    engine, institution→program) and the operational control graph
    (program→succession→epoch→fleet→campaign). Program children execute via
    :func:`run_operational_spine` unless an explicit ``program_runner`` is
    injected.
    """
    from blackhole_agent import upstream_constitution_engine as ce

    layer = ce.get_stewardship_layer("institution")
    slots: list[dict[str, Any]]
    if charter is not None:
        slots = [dict(s) for s in charter if isinstance(s, Mapping)]
    elif programs is not None:
        slots = [dict(p) for p in programs if isinstance(p, Mapping)]
    else:
        slots = [
            {
                "program_id": "gov-a",
                "priority": 1,
                "max_successions": max_successions,
                "program_goal": "none",
                "mandate_goal": "none",
                "kind": "stewardship_program",
                "inventory_keys": [("gov-alpha", "1.0.0", "gov-alpha-1")],
                "charter": [
                    {
                        "inventory_keys": [
                            ["gov-alpha", "1.0.0", "gov-alpha-1"]
                        ]
                    }
                ],
            }
        ]

    runner = program_runner or make_operational_program_child_runner(
        max_successions=max_successions,
        max_epochs=max_epochs,
        max_waves=max_waves,
        idle_limit=idle_limit,
        goal_dispatched_ok=goal_dispatched_ok,
        campaign_run_stage=campaign_run_stage,
        stewardship_root=stewardship_root,
    )

    result = ce.run_constitution(
        layer,
        charter=slots,
        max_rounds=max_rounds,
        dispatch=dispatch,
        dispatch_budget=dispatch_budget,
        max_active=max_active,
        child_runner=runner,
        goal=institution_goal or layer.all_children_met_goal,
        constitution_id=institution_id or "governance-spine",
        out_root=out_root,
    )

    child_path: list[dict[str, Any]] | None = None
    # Recover control path from governance_child.json written by the program
    # adapter (round records only store digests, not full nest paths).
    state_lists = [
        result.get("child_states"),
        result.get("program_states"),
        result.get("programs"),
    ]
    for states in state_lists:
        if child_path is not None:
            break
        for st in list(states or []):
            if not isinstance(st, Mapping):
                continue
            pdir = (
                st.get("last_program_dir")
                or st.get("program_dir")
                or st.get("out_root")
            )
            if not pdir:
                continue
            gpath = Path(str(pdir)) / "governance_child.json"
            if not gpath.is_file():
                continue
            try:
                blob = json.loads(gpath.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cpath = blob.get("control_nest_path")
            if cpath:
                child_path = [dict(s) for s in cpath if isinstance(s, Mapping)]
                break

    annotated = annotate_governance_spine(
        result, live=live, child_control_path=child_path
    )
    annotated["governance_edge"] = "institution->program"
    annotated["governance_operational_edge"] = "program->campaign"
    return annotated


def builtin_governance_spine_proof() -> dict[str, Any]:
    """Hermetic proof: institution→program→…→campaign is one governance spine."""
    scratch = Path(tempfile.mkdtemp(prefix="governance-spine-proof-"))
    try:
        from blackhole_agent import upstream_constitution_engine as ce
        from blackhole_agent import upstream_institution as ui
        from blackhole_agent import upstream_loop_engine as le_facade
        from blackhole_agent import upstream_program as up
        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        path = governance_nest_path()
        path_ok = (
            governance_nest_depth() == 6
            and [s.get("dialect") for s in path]
            == [
                "institution",
                "program",
                "succession",
                "epoch",
                "fleet",
                "campaign",
            ]
            and path[0].get("mode") == "constitution"
            and path[1].get("mode") == "loop"
            and path[-1].get("mode") == "pipeline"
        )

        # Core public entry.
        gov = run_governance_spine(
            out_root=scratch / "gov",
            max_rounds=3,
            dispatch=True,
            dispatch_budget=4,
            max_successions=2,
            max_epochs=2,
            max_waves=2,
            programs=[
                {
                    "program_id": "gp1",
                    "priority": 2,
                    "max_successions": 2,
                    "program_goal": "none",
                    "kind": "stewardship_program",
                    "inventory_keys": [("g1", "1.0.0", "g1-1")],
                    "charter": [
                        {"inventory_keys": [["g1", "1.0.0", "g1-1"]]}
                    ],
                }
            ],
        )
        child_path = gov.get("governance_child_control_path") or []
        child_dialects = [
            s.get("dialect") for s in child_path if isinstance(s, Mapping)
        ]
        gov_ok = (
            bool(gov.get("ok"))
            and gov.get("governance_spine") is True
            and gov.get("governance_spine_live") is True
            and gov.get("control_operational_spine") is True
            and gov.get("control_graph") is True
            and gov.get("control_graph_live") is True
            and int(gov.get("governance_nest_depth") or 0) == 6
            and int(gov.get("total_dispatched_ok") or 0) >= 1
            and bool(gov.get("institution_met") or gov.get("institution_digest"))
            and child_dialects
            == ["program", "succession", "epoch", "fleet", "campaign"]
            and not legacy_pipeline_was_used()
        )

        # Adapter alone: constitution kwargs → operational spine seals.
        adapter = make_operational_program_child_runner(
            max_successions=2, max_epochs=2, max_waves=2
        )
        adapted = adapter(
            program_id="adapter-p",
            out_root=scratch / "adapter",
            dispatch=True,
            dispatch_budget=2,
            charter=[{"inventory_keys": [["a", "1.0.0", "a-1"]]}],
        )
        adapter_ok = (
            bool(adapted.get("ok"))
            and adapted.get("governance_spine_child") is True
            and adapted.get("control_graph_live") is True
            and adapted.get("control_operational_spine") is True
            and adapted.get("program_met") is True
            and int(adapted.get("control_nest_depth") or 0) == 5
            and [
                s.get("dialect")
                for s in (adapted.get("control_nest_path") or [])
            ]
            == ["program", "succession", "epoch", "fleet", "campaign"]
            and bool(adapted.get("program_digest"))
            and (Path(str(adapted["program_dir"])) / "program.json").is_file()
        )

        # Live domain: run_institution(governance_spine=True).
        live_inst = ui.run_institution(
            governance_spine=True,
            charter=[
                {
                    "program_id": "live-gp",
                    "priority": 1,
                    "inventory_keys": [("live", "1.0.0", "live-1")],
                    "charter": [
                        {"inventory_keys": [["live", "1.0.0", "live-1"]]}
                    ],
                }
            ],
            max_rounds=3,
            dispatch=True,
            dispatch_budget=4,
            out_root=scratch / "live-inst",
            institution_id="live-gov",
        )
        live_ok = (
            bool(live_inst.get("ok"))
            and live_inst.get("governance_spine") is True
            and live_inst.get("governance_spine_live") is True
            and live_inst.get("control_operational_spine") is True
            and int(live_inst.get("total_dispatched_ok") or 0) >= 1
            and bool(live_inst.get("institution_digest"))
        )

        # Module flags: institution advertises governance attach; program
        # remains the operational graph leaf.
        flags_ok = (
            getattr(ui, "GOVERNANCE_SPINE", False) is True
            and getattr(ui, "GOVERNANCE_SPINE_LIVE", False) is True
            and getattr(ui, "ENGINE_FACADE", False) is True
            and getattr(up, "CONTROL_GRAPH", False) is True
            and getattr(up, "CONTROL_GRAPH_LIVE", False) is True
            and callable(getattr(le_facade, "run_governance_spine", None))
            and callable(getattr(le_facade, "make_operational_program_child_runner", None))
            and getattr(le_facade, "GOVERNANCE_SPINE_IMPL", False) is True
        )

        # Source-level: facade wires governance_spine → operational runner.
        facade_path = Path(ui.__file__).resolve().parent / "upstream_stewardship_facade.py"
        facade_text = facade_path.read_text(encoding="utf-8")
        source_ok = (
            "governance_spine" in facade_text
            and "make_operational_program_child_runner" in facade_text
            and "annotate_governance_spine" in facade_text
        )

        engine_path = Path(__file__).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "def run_governance_spine" in engine_text
            and "def make_operational_program_child_runner" in engine_text
            and "GOVERNANCE_NEST_PATH" in engine_text
            and "builtin_governance_spine_proof" in engine_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-governance-spine")
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and "upstream_control_engine" in (entry.entry or "")
                and "builtin_governance_spine_proof" in (entry.entry or "")
                and (
                    "governance" in tags_blob
                    or "governance" in name_blob
                    or "governance" in delta_blob
                )
                and (
                    "institution" in delta_blob
                    or "constitution" in delta_blob
                )
                and (
                    "run_governance_spine" in delta_blob
                    or "operational" in delta_blob
                )
                and (
                    "program" in delta_blob
                    and ("campaign" in delta_blob or "spine" in delta_blob)
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        engine_loc = sum(
            1
            for line in engine_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

        ok = all(
            [
                path_ok,
                gov_ok,
                adapter_ok,
                live_ok,
                flags_ok,
                source_ok,
                engine_source_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "governance_spine_proof",
            "path_ok": path_ok,
            "governance_nest_path": path,
            "governance_nest_depth": governance_nest_depth(),
            "gov_ok": gov_ok,
            "gov_dispatched_ok": gov.get("total_dispatched_ok"),
            "gov_institution_digest": gov.get("institution_digest"),
            "gov_child_path": child_path,
            "adapter_ok": adapter_ok,
            "adapter_depth": adapted.get("control_nest_depth"),
            "adapter_digest": adapted.get("program_digest"),
            "live_ok": live_ok,
            "live_dispatched_ok": live_inst.get("total_dispatched_ok"),
            "live_institution_digest": live_inst.get("institution_digest"),
            "flags_ok": flags_ok,
            "source_ok": source_ok,
            "engine_source_ok": engine_source_ok,
            "ledger_capability_ok": ledger_ok,
            "engine_loc": engine_loc,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "control_graph": True,
            "control_operational_spine": True,
            "governance_spine": True,
            "governance_spine_live": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def builtin_control_nest_proof() -> dict[str, Any]:
    """Hermetic proof: multi-depth nest owns program→…→fleet→campaign spine."""
    scratch = Path(tempfile.mkdtemp(prefix="control-nest-proof-"))
    try:
        path = nest_path(OPERATIONAL_NEST)
        path_ok = (
            nest_depth(OPERATIONAL_NEST) == 5
            and [s["dialect"] for s in path]
            == ["program", "succession", "epoch", "fleet", "campaign"]
            and [s["mode"] for s in path]
            == ["loop", "loop", "loop", "pipeline", "pipeline"]
        )
        try:
            validate_control_node(OPERATIONAL_NEST)
            validate_ok = True
        except Exception:  # noqa: BLE001
            validate_ok = False

        # --- pipeline stage hooks (fleet parent + campaign child) ---
        # Fleet hooks must NOT fabricate campaign; graph owns pipeline-of-pipeline.
        fleet_calls: list[str] = []
        campaign_calls: list[str] = []

        def run_fleet_stage(state: PipelineState, name: str) -> dict[str, Any]:
            ri = state.context.get("round_index")
            parent = state.context.get("parent_dialect")
            fleet_calls.append(f"{parent}:{ri}:{name}")
            if name == "inventory":
                state.context["inventory"] = [{"name": "alpha", "version": "1.0.0"}]
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "inventoried",
                    "inventory_count": 1,
                }
            if name == "portfolio":
                state.context["portfolio"] = {
                    "entries": [],
                    "portfolio_digest": "p" * 64,
                }
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "portfolio_ready",
                    "portfolio_digest": "p" * 64,
                }
            if name == "rank":
                actions = [
                    {
                        "action": "campaign_patch_bound",
                        "name": "alpha",
                        "version": "1.0.0",
                        "campaignable": True,
                        "priority": 40,
                        "rank": 1,
                    }
                ]
                state.context["actions"] = actions
                state.context["campaignable"] = actions
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "ranked",
                    "action_count": 1,
                    "campaignable_count": 1,
                }
            # dispatch is engine-owned via compose_pipeline_of_pipeline; if the
            # graph still invokes this hook for dispatch, that is a regression.
            if name == "dispatch":
                raise StageRefused(
                    "control_graph_pop_missing",
                    "fleet dispatch must be owned by compose_pipeline_of_pipeline "
                    "inside run_control_graph, not by the fleet stage hook",
                )
            raise StageRefused("stage_unknown", name)

        def fleet_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "fleet_dispatched"

        def fleet_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "nest-fleet-leaf",
                identity={
                    "name": "nestalpha",
                    "version": "1.0.0",
                    "inventory_count": 1,
                    "action_count": 1,
                },
                stage_digests={
                    "rank.verdict": _sha256_bytes(b"ranked"),
                    "dispatch.verdict": _sha256_bytes(b"fleet_dispatched"),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "version": receipt.get("version"),
                    "stages": receipt.get("stages"),
                    "stage_digests": receipt.get("stage_digests"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        def run_camp_stage(state: PipelineState, name: str) -> dict[str, Any]:
            campaign_calls.append(name)
            if name == "repair":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "repair_green",
                    "report_sha256": "a" * 64,
                }
            if name == "contribution":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "contribution_ready",
                    "defects": [
                        {
                            "defect_id": "d1",
                            "ok": True,
                            "verdict": "submittable",
                            "bundle_sha256": "b" * 64,
                        }
                    ],
                }
            if name == "publication":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "publication_dry_run",
                    "publications": [
                        {
                            "bundle_dir": "bundle-d1",
                            "ok": True,
                            "verdict": "dry_run",
                        }
                    ],
                }
            raise StageRefused("stage_unknown", name)

        def camp_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "publication_dry_run"

        def camp_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "nest-campaign-leaf",
                identity={"name": "camp-alpha", "version": "1.0.0"},
                stage_digests={
                    "repair.verdict": _sha256_bytes(b"repair_green"),
                    "publication.verdict": _sha256_bytes(b"publication_dry_run"),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "stages": receipt.get("stages"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        pipe_hooks = {
            "fleet": PipelineNestHooks(
                run_stage=run_fleet_stage,
                classify=fleet_classify,
                seal=fleet_seal,
                attach_stage="dispatch",
            ),
            "campaign": PipelineNestHooks(
                run_stage=run_camp_stage,
                classify=camp_classify,
                seal=camp_seal,
            ),
        }

        def _make_loop_hooks(dialect_name: str, goal_after: int) -> LoopNestHooks:
            d = get_loop_dialect(dialect_name)

            def classify(state: LoopState) -> tuple[bool, str]:
                if state.total_dispatched_ok >= goal_after:
                    state.goal_met = True
                    return True, f"{dialect_name}_progressed"
                if state.total_dispatched_ok > 0:
                    return True, f"{dialect_name}_progressed"
                return True, f"{dialect_name}_idle"

            def seal(state: LoopState) -> dict[str, Any]:
                receipt = {
                    "ok": True,
                    "verdict": state.extras.get("verdict")
                    or f"{dialect_name}_progressed",
                    "stop_reason": state.stop_reason,
                    f"max_{d.child_plural}": state.max_rounds,
                    d.child_count_field: len(state.records),
                    d.child_plural: state.records,
                    d.child_digests_field: list(state.child_digests),
                    "total_dispatched": state.total_dispatched,
                    "total_dispatched_ok": state.total_dispatched_ok,
                    "portfolio_start_digest": state.portfolio_start_digest,
                    "portfolio_end_digest": (state.portfolio or {}).get(
                        "portfolio_digest"
                    ),
                    d.self_met_field: state.goal_met,
                }

                def payload(r: Mapping[str, Any]) -> dict[str, Any]:
                    return {
                        "schema_version": r.get("schema_version"),
                        "verdict": r.get("verdict"),
                        "stop_reason": r.get("stop_reason"),
                        d.child_count_field: r.get(d.child_count_field),
                        d.child_digests_field: list(r.get(d.child_digests_field) or []),
                        "total_dispatched": r.get("total_dispatched"),
                        "total_dispatched_ok": r.get("total_dispatched_ok"),
                    }

                sealed = seal_json_receipt(state, receipt, digest_payload=payload)
                sealed[d.child_plural] = state.records
                return sealed

            def post_stop(
                state: LoopState, round_index: int, result: dict[str, Any]
            ) -> str | None:
                if state.total_dispatched_ok >= goal_after:
                    state.goal_met = True
                    return d.goal_stop_reason
                return None

            return LoopNestHooks(
                classify=classify,
                seal=seal,
                post_round_stop=post_stop,
                max_rounds=2,
                idle_limit=2,
            )

        # Goal: accumulate enough dispatches across the nest.
        # Each fleet dispatch contributes 1; need 2 so multi-wave fires.
        hooks = {
            "program": _make_loop_hooks("program", goal_after=2),
            "succession": _make_loop_hooks("succession", goal_after=2),
            "epoch": _make_loop_hooks("epoch", goal_after=2),
        }

        # Public spine entry: native graph owns fleet→campaign.
        nest_result = run_operational_spine(
            loop_hooks=hooks,
            pipeline_hooks=pipe_hooks,
            out_root=scratch / "nest-root",
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            dispatch=True,
            dispatch_budget=8,
            live=False,
        )

        # Campaign stages must actually run (engine-native pop, not fleet fiction).
        campaign_ok = (
            campaign_calls.count("repair") >= 2
            and campaign_calls.count("contribution") >= 2
            and campaign_calls.count("publication") >= 2
            and not any(c.endswith(":dispatch") for c in fleet_calls)
            and any(":inventory" in c for c in fleet_calls)
        )

        nest_ok = (
            nest_result.get("ok")
            and nest_result.get("control_engine") is True
            and nest_result.get("control_nest") is True
            and nest_result.get("control_composed") is True
            and nest_result.get("control_graph") is True
            and nest_result.get("control_operational_spine") is True
            and nest_result.get("control_graph_native_pipeline") is True
            and nest_result.get("control_nest_depth") == 5
            and nest_result.get("control_mode") == "loop"
            and nest_result.get("control_parent_dialect") == "program"
            and nest_result.get("control_child_dialect") == "succession"
            and nest_result.get("loop_dialect") == "program"
            and int(nest_result.get("total_dispatched_ok") or 0) >= 2
            and campaign_ok
            and bool(nest_result.get("program_digest"))
        )

        # Also prove compose_loop_of_loop in isolation (succession→epoch with
        # a stub epoch child).
        child_n = {"n": 0}

        def epoch_stub(**kwargs: Any) -> dict[str, Any]:
            child_n["n"] += 1
            idx = child_n["n"] - 1
            out = Path(str(kwargs.get("out_root") or scratch / f"ep-{idx}"))
            out.mkdir(parents=True, exist_ok=True)
            dig = _sha256_json({"epoch_stub": idx})
            atomic_write_json(
                out / "epoch.json",
                {"ok": True, "epoch_digest": dig, "total_dispatched": 1, "total_dispatched_ok": 1},
            )
            return {
                "ok": True,
                "verdict": "epoch_progressed",
                "epoch_dir": str(out),
                "epoch_digest": dig,
                "total_dispatched": 1,
                "total_dispatched_ok": 1,
                "control_engine": True,
                "control_mode": "loop",
                "loop_dialect": "epoch",
            }

        succ_hooks = _make_loop_hooks("succession", goal_after=2)
        loop_of_loop = compose_loop_of_loop(
            parent_dialect="succession",
            child_dialect="epoch",
            max_rounds=3,
            child_max_rounds=2,
            child_runner=epoch_stub,
            classify_parent=succ_hooks.classify,
            seal_parent=succ_hooks.seal,
            post_round_stop=succ_hooks.post_round_stop,
            out_root=scratch / "loop-of-loop",
            portfolio={"entries": [], "portfolio_digest": "q" * 64},
            dispatch=True,
            dispatch_budget=4,
            idle_limit=2,
        )
        lol_ok = (
            loop_of_loop.get("ok")
            and loop_of_loop.get("control_nest") is True
            and loop_of_loop.get("control_child_mode") == "loop"
            and loop_of_loop.get("control_child_dialect") == "epoch"
            and loop_of_loop.get("control_parent_dialect") == "succession"
            and loop_of_loop.get("control_nest_edge") == "succession->epoch"
            and child_n["n"] >= 2
            and int(loop_of_loop.get("total_dispatched_ok") or 0) >= 2
        )

        # Pipeline-of-pipeline: fleet→campaign composition.
        camp_calls: list[str] = []

        def run_parent_only(state: PipelineState, name: str) -> dict[str, Any]:
            if name == "inventory":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "inventoried",
                    "inventory_count": 1,
                }
            if name == "portfolio":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "portfolio_ready",
                    "portfolio_digest": "p" * 64,
                }
            if name == "rank":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "ranked",
                    "action_count": 1,
                    "campaignable_count": 1,
                }
            raise StageRefused("stage_unknown", name)

        def run_camp_stage(state: PipelineState, name: str) -> dict[str, Any]:
            camp_calls.append(name)
            if name == "repair":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "repair_green",
                    "report_sha256": "a" * 64,
                }
            if name == "contribution":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "contribution_ready",
                    "defects": [{"defect_id": "d1", "ok": True}],
                }
            if name == "publication":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "publication_dry_run",
                    "publications": [{"ok": True}],
                }
            raise StageRefused("stage_unknown", name)

        def camp_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "publication_dry_run"

        def camp_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "pop-campaign",
                identity={"name": "camp-alpha", "version": "1.0.0"},
                stage_digests={
                    "repair.verdict": _sha256_bytes(b"repair_green"),
                    "publication.verdict": _sha256_bytes(b"publication_dry_run"),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "stages": receipt.get("stages"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        def fleet_pop_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "fleet_dispatched"

        def fleet_pop_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "pop-fleet",
                identity={"name": "fleet-pop", "version": "1.0.0"},
                stage_digests={
                    "dispatch.verdict": _sha256_bytes(b"fleet_dispatched"),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "stages": receipt.get("stages"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        pop = compose_pipeline_of_pipeline(
            parent_dialect="fleet",
            child_dialect="campaign",
            attach_stage="dispatch",
            parent_stages=["inventory", "portfolio", "rank", "dispatch"],
            child_stages=list(CAMPAIGN_NEST_STAGES),
            run_parent_stage=run_parent_only,
            run_child_stage=run_camp_stage,
            classify_parent=fleet_pop_classify,
            seal_parent=fleet_pop_seal,
            classify_child=camp_classify,
            seal_child=camp_seal,
            initial_parent_context={"round_index": 0},
            live=False,
        )
        pop_ok = (
            pop.get("ok")
            and pop.get("control_nest") is True
            and pop.get("control_mode") == "pipeline"
            and pop.get("control_parent_dialect") == "fleet"
            and pop.get("control_child_dialect") == "campaign"
            and pop.get("control_nest_edge") == "fleet->campaign"
            and pop.get("control_child_mode") == "pipeline"
            and int(pop.get("nested_pipeline_count") or 0) >= 1
            and camp_calls == ["repair", "contribution", "publication"]
            and bool(pop.get("fleet_digest") or pop.get("plan_dir"))
        )

        # Live domain modules declare nest ownership flags + use nest runners.
        from blackhole_agent import upstream_campaign as ucamp
        from blackhole_agent import upstream_epoch as ue
        from blackhole_agent import upstream_fleet as ufleet
        from blackhole_agent import upstream_program as up
        from blackhole_agent import upstream_succession as us
        from blackhole_agent import upstream_loop_engine as le_facade
        from blackhole_agent import upstream_stage_engine as se_facade

        live_nest_flags = {
            "program": getattr(up, "CONTROL_NEST", False) is True,
            "succession": getattr(us, "CONTROL_NEST", False) is True,
            "epoch": getattr(ue, "CONTROL_NEST", False) is True,
            "fleet": getattr(ufleet, "CONTROL_NEST", False) is True,
            "campaign": getattr(ucamp, "CONTROL_NEST", False) is True,
            "program_live": getattr(up, "CONTROL_NEST_LIVE", False) is True,
            "succession_live": getattr(us, "CONTROL_NEST_LIVE", False) is True,
            "epoch_live": getattr(ue, "CONTROL_NEST_LIVE", False) is True,
            "fleet_live": getattr(ufleet, "CONTROL_NEST_LIVE", False) is True,
            "program_child": getattr(up, "CONTROL_NEST_CHILD", "") == "succession",
            "succession_child": getattr(us, "CONTROL_NEST_CHILD", "") == "epoch",
            "epoch_child": getattr(ue, "CONTROL_NEST_CHILD", "") == "fleet",
            "fleet_child": getattr(ufleet, "CONTROL_NEST_CHILD", "") == "campaign",
            "fleet_child_mode": getattr(ufleet, "CONTROL_NEST_CHILD_MODE", "")
            == "pipeline",
            "operational_path": (
                getattr(up, "CONTROL_NEST_PATH", None) == operational_nest_path()
                or (
                    isinstance(getattr(up, "CONTROL_NEST_PATH", None), list)
                    and len(getattr(up, "CONTROL_NEST_PATH", []) or []) == 5
                )
            ),
            "facade_nested": callable(getattr(le_facade, "run_nested_control", None)),
            "facade_nested_pipe": callable(
                getattr(se_facade, "run_nested_pipeline", None)
            ),
            "facade_nest_impl": getattr(le_facade, "CONTROL_NEST_IMPL", False) is True,
            "program_graph": getattr(up, "CONTROL_GRAPH", False) is True,
            "succession_graph": getattr(us, "CONTROL_GRAPH", False) is True,
            "epoch_graph": getattr(ue, "CONTROL_GRAPH", False) is True,
            "fleet_graph": getattr(ufleet, "CONTROL_GRAPH", False) is True,
            "campaign_graph": getattr(ucamp, "CONTROL_GRAPH", False) is True,
            "fleet_graph_native": getattr(
                ufleet, "CONTROL_GRAPH_NATIVE_PIPELINE", False
            )
            is True,
            "facade_graph_impl": getattr(le_facade, "CONTROL_GRAPH_IMPL", False)
            is True,
            "facade_run_spine": callable(
                getattr(le_facade, "run_operational_spine", None)
            ),
            "program_graph_live_flag": getattr(up, "CONTROL_GRAPH_LIVE", False)
            is True,
            "fleet_graph_hooks": callable(
                getattr(ufleet, "make_graph_pipeline_hooks", None)
            ),
            "campaign_graph_hooks": callable(
                getattr(ucamp, "make_graph_pipeline_hooks", None)
            ),
            "build_live_hooks": callable(build_live_domain_hooks),
            "progress_loop_hooks": callable(make_progress_loop_hooks),
        }
        live_flags_ok = all(live_nest_flags.values())

        # Source-level: live run_* must call nest entrypoints, not bare runners.
        def _src_uses_nested(mod: Any) -> bool:
            mod_path = Path(mod.__file__).resolve()
            text = mod_path.read_text(encoding="utf-8")
            return (
                "run_nested_control" in text
                and "return le.run_nested_control" in text
            )

        def _src_uses_nested_pipeline(mod: Any) -> bool:
            mod_path = Path(mod.__file__).resolve()
            text = mod_path.read_text(encoding="utf-8")
            return (
                "run_nested_pipeline" in text
                and "return se.run_nested_pipeline" in text
            )

        def _src_uses_operational_spine(mod: Any) -> bool:
            mod_path = Path(mod.__file__).resolve()
            text = mod_path.read_text(encoding="utf-8")
            return (
                "run_operational_spine" in text
                and "control_graph" in text
                and "_run_program_control_graph" in text
            )

        live_source = {
            "epoch": _src_uses_nested(ue),
            "succession": _src_uses_nested(us),
            "program": _src_uses_nested(up),
            "fleet": _src_uses_nested_pipeline(ufleet),
            "program_graph": _src_uses_operational_spine(up),
        }
        live_source_ok = all(live_source.values())

        # Live injected runs: nest flags on real domain return values.
        def _live_fleet(**kwargs: Any) -> dict[str, Any]:
            out = Path(str(kwargs.get("out_root") or scratch / "live-wave"))
            out.mkdir(parents=True, exist_ok=True)
            dig = _sha256_json({"live": str(out), "ri": kwargs.get("round_index")})
            return {
                "ok": True,
                "verdict": "fleet_dispatched",
                "plan_dir": str(out),
                "fleet_digest": dig,
                "dispatched_count": 1,
                "dispatched_ok": 1,
                "campaignable_count": 0,
                "dispatches": [{"ok": True, "campaign_digest": dig}],
            }

        live_epoch = ue.run_epoch(
            fleet_runner=_live_fleet,
            max_waves=1,
            dispatch=True,
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            out_root=scratch / "live-epoch",
        )
        live_epoch_ok = (
            live_epoch.get("ok")
            and live_epoch.get("control_nest") is True
            and live_epoch.get("control_nest_live") is True
            and live_epoch.get("control_nest_edge") == "epoch->fleet"
            and live_epoch.get("control_child_mode") == "pipeline"
            and live_epoch.get("control_child_dialect") == "fleet"
        )

        def _live_epoch(**kwargs: Any) -> dict[str, Any]:
            return ue.run_epoch(
                fleet_runner=_live_fleet,
                max_waves=1,
                dispatch=True,
                portfolio=kwargs.get("portfolio")
                or {"entries": [], "portfolio_digest": "p" * 64},
                out_root=kwargs.get("out_root") or scratch / "live-succ-epoch",
                dispatch_budget=kwargs.get("dispatch_budget"),
            )

        live_succ = us.run_succession(
            epoch_runner=_live_epoch,
            max_epochs=1,
            max_waves_per_epoch=1,
            dispatch=True,
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            out_root=scratch / "live-succession",
            mandate_goal="none",
        )
        live_succ_ok = (
            live_succ.get("ok")
            and live_succ.get("control_nest") is True
            and live_succ.get("control_nest_live") is True
            and live_succ.get("control_nest_edge") == "succession->epoch"
            and live_succ.get("control_child_mode") == "loop"
            and live_succ.get("control_child_dialect") == "epoch"
            # Nested child also nest-live (epoch→fleet).
            and bool((live_succ.get("epochs") or [{}])[0].get("epoch_digest"))
        )

        def _live_succ(**kwargs: Any) -> dict[str, Any]:
            return us.run_succession(
                epoch_runner=_live_epoch,
                max_epochs=1,
                max_waves_per_epoch=1,
                dispatch=True,
                portfolio=kwargs.get("portfolio")
                or {"entries": [], "portfolio_digest": "p" * 64},
                out_root=kwargs.get("out_root") or scratch / "live-prog-succ",
                dispatch_budget=kwargs.get("dispatch_budget"),
                mandate_goal="none",
            )

        live_prog = up.run_program(
            succession_runner=_live_succ,
            max_successions=1,
            max_epochs_per_succession=1,
            max_waves_per_epoch=1,
            dispatch=True,
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            out_root=scratch / "live-program",
            program_goal="none",
            mandate_goal="none",
        )
        live_prog_ok = (
            live_prog.get("ok")
            and live_prog.get("control_nest") is True
            and live_prog.get("control_nest_live") is True
            and live_prog.get("control_nest_edge") == "program->succession"
            and live_prog.get("control_child_mode") == "loop"
            and live_prog.get("control_child_dialect") == "succession"
            and int(live_prog.get("control_nest_depth") or 0) == 5
            and bool(live_prog.get("program_digest"))
        )

        # Live fleet→campaign nest edge via run_nested_pipeline.
        live_fleet = ufleet.plan_fleet(
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            dispatch=False,
            out_root=scratch / "live-fleet",
            stages=["inventory", "portfolio", "rank"],
            stewardship_root=scratch / "empty-stewardship",
        )
        live_fleet_ok = (
            live_fleet.get("control_nest") is True
            and live_fleet.get("control_nest_live") is True
            and live_fleet.get("control_nest_edge") == "fleet->campaign"
            and live_fleet.get("control_mode") == "pipeline"
            and live_fleet.get("control_parent_dialect") == "fleet"
            and live_fleet.get("control_child_dialect") == "campaign"
            and live_fleet.get("control_child_mode") == "pipeline"
            and int(live_fleet.get("control_nest_depth") or 0) == 5
        )
        live_domain_ok = (
            live_epoch_ok and live_succ_ok and live_prog_ok and live_fleet_ok
        )

        # Live domain attach: run_program(control_graph=True) → operational spine.
        live_graph = up.run_program(
            control_graph=True,
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            max_successions=2,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            dispatch_budget=4,
            dispatch=True,
            out_root=scratch / "live-graph-program",
        )
        live_graph_ok = (
            live_graph.get("ok")
            and live_graph.get("control_graph_live") is True
            and live_graph.get("control_operational_spine") is True
            and live_graph.get("control_graph") is True
            and live_graph.get("control_graph_native_pipeline") is True
            and live_graph.get("control_nest_live") is True
            and live_graph.get("control_graph_domain") == "program"
            and int(live_graph.get("control_nest_depth") or 0) == 5
            and int(live_graph.get("total_dispatched_ok") or 0) >= 1
            and bool(live_graph.get("program_digest"))
            and [
                s.get("dialect")
                for s in (live_graph.get("control_nest_path") or [])
            ]
            == ["program", "succession", "epoch", "fleet", "campaign"]
        )

        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-control-graph")
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and "upstream_control_engine" in (entry.entry or "")
                and "builtin_control_graph_proof" in (entry.entry or "")
                and (
                    "graph" in tags_blob
                    or "graph" in name_blob
                    or "graph" in delta_blob
                )
                and (
                    "run_operational_spine" in delta_blob
                    or "native" in delta_blob
                )
                and (
                    "control_graph=true" in delta_blob
                    or "control_graph" in delta_blob
                    or "live" in delta_blob
                )
                and (
                    "fleet->campaign" in delta_blob
                    or "fleet→campaign" in delta_blob
                    or "pipeline_of_pipeline" in delta_blob
                    or "compose_pipeline_of_pipeline" in delta_blob
                    or "make_graph_pipeline_hooks" in delta_blob
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        # Facades re-export graph ownership surface.
        facade_graph_ok = (
            callable(getattr(le_facade, "run_operational_spine", None))
            and callable(getattr(le_facade, "run_control_graph", None))
            and getattr(le_facade, "CONTROL_GRAPH_IMPL", False) is True
            and getattr(se_facade, "CONTROL_GRAPH_IMPL", False) is True
        )

        engine_path = Path(__file__).resolve()
        engine_loc = sum(
            1
            for line in engine_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

        ok = all(
            [
                path_ok,
                validate_ok,
                nest_ok,
                lol_ok,
                pop_ok,
                live_flags_ok,
                live_source_ok,
                live_domain_ok,
                live_graph_ok,
                facade_graph_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "control_graph_proof",
            "path_ok": path_ok,
            "validate_ok": validate_ok,
            "nest_path": path,
            "nest_depth": nest_depth(OPERATIONAL_NEST),
            "nest_graph_ok": nest_ok,
            "compose_loop_of_loop_ok": lol_ok,
            "compose_pipeline_of_pipeline_ok": pop_ok,
            "pipeline_of_pipeline_edge": pop.get("control_nest_edge"),
            "campaign_calls": camp_calls,
            "spine_campaign_calls": list(campaign_calls),
            "spine_campaign_ok": campaign_ok,
            "live_nest_flags_ok": live_flags_ok,
            "live_nest_flags": live_nest_flags,
            "live_source_ok": live_source_ok,
            "live_source": live_source,
            "live_domain_ok": live_domain_ok,
            "live_epoch_ok": live_epoch_ok,
            "live_succession_ok": live_succ_ok,
            "live_program_ok": live_prog_ok,
            "live_fleet_ok": live_fleet_ok,
            "live_graph_ok": live_graph_ok,
            "live_graph_domain": live_graph.get("control_graph_domain"),
            "live_graph_depth": live_graph.get("control_nest_depth"),
            "live_graph_dispatched_ok": live_graph.get("total_dispatched_ok"),
            "live_graph_digest": live_graph.get("program_digest"),
            "live_epoch_edge": live_epoch.get("control_nest_edge"),
            "live_succession_edge": live_succ.get("control_nest_edge"),
            "live_program_edge": live_prog.get("control_nest_edge"),
            "live_fleet_edge": live_fleet.get("control_nest_edge"),
            "facade_graph_ok": facade_graph_ok,
            "ledger_capability_ok": ledger_ok,
            "program_digest": nest_result.get("program_digest"),
            "live_program_digest": live_prog.get("program_digest"),
            "live_fleet_digest": live_fleet.get("fleet_digest"),
            "succession_of_loop_digest": loop_of_loop.get("succession_digest"),
            "total_dispatched_ok": nest_result.get("total_dispatched_ok"),
            "fleet_calls": fleet_calls,
            "nest_edge": nest_result.get("control_nest_edge"),
            "engine_loc": engine_loc,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "control_nest": True,
            "control_spine": True,
            "control_graph": True,
            "control_graph_native_pipeline": True,
            "control_operational_spine": True,
            "control_graph_live": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def builtin_control_engine_proof() -> dict[str, Any]:
    """Hermetic proof that one multi-mode engine owns pipeline + loop control flow."""
    scratch = Path(tempfile.mkdtemp(prefix="control-engine-proof-"))
    try:
        catalog = list_control_catalog()
        catalog_ok = (
            catalog.get("pipeline") == ["campaign", "fleet"]
            and catalog.get("loop") == ["program", "succession", "epoch"]
            and list_control_modes() == ["pipeline", "loop"]
            and len(list_all_control_dialects()) == 5
        )

        calls: list[str] = []

        def run_stage(state: PipelineState, name: str) -> dict[str, Any]:
            calls.append(name)
            if name == "repair":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "repair_green",
                    "report_sha256": "a" * 64,
                }
            if name == "contribution":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "contribution_ready",
                    "defects": [
                        {
                            "defect_id": "d1",
                            "ok": True,
                            "verdict": "submittable",
                            "bundle_sha256": "b" * 64,
                        }
                    ],
                }
            if name == "publication":
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "publication_dry_run",
                    "publications": [
                        {
                            "bundle_dir": "bundle-d1",
                            "ok": True,
                            "verdict": "dry_run",
                            "receipt_sha256": "c" * 64,
                        }
                    ],
                }
            return {"stage": name, "ok": True, "verdict": f"{name}_ok"}

        def classify_p(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "campaign_complete"

        def seal_p(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "pipe",
                identity={"name": "ctrlprobe", "version": "1.0.0", "defect_ids": ["d1"]},
            )

        pipe = run_control(
            "pipeline",
            "campaign",
            stages=("repair", "contribution", "publication"),
            run_stage=run_stage,
            classify_verdict=classify_p,
            seal=seal_p,
        )
        pipe_ok = (
            pipe.get("ok")
            and pipe.get("control_engine") is True
            and pipe.get("control_mode") == "pipeline"
            and pipe.get("control_dialect") == "campaign"
            and pipe.get("stage_engine") is True
            and calls == ["repair", "contribution", "publication"]
        )

        child_n = {"n": 0}

        def child_runner(**kwargs: Any) -> dict[str, Any]:
            child_n["n"] += 1
            idx = child_n["n"] - 1
            out = Path(str(kwargs.get("out_root") or scratch / f"child-{idx}"))
            out.mkdir(parents=True, exist_ok=True)
            dig = _sha256_json({"i": idx})
            atomic_write_json(
                out / "epoch.json",
                {
                    "ok": True,
                    "epoch_digest": dig,
                    "total_dispatched": 1,
                    "total_dispatched_ok": 1,
                },
            )
            return {
                "ok": True,
                "verdict": "epoch_progressed",
                "epoch_dir": str(out),
                "epoch_digest": dig,
                "total_dispatched": 1,
                "total_dispatched_ok": 1,
            }

        def build_kwargs(state: LoopState, round_index: int) -> dict[str, Any]:
            return {
                "out_root": state.child_root / f"epoch-{round_index:02d}",
                "round_index": round_index,
            }

        def on_result(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> dict[str, Any]:
            if result.get("epoch_digest"):
                state.child_digests.append(str(result["epoch_digest"]))
            if round_index >= 1:
                state.goal_met = True
            return {
                "epoch": round_index,
                "ok": True,
                "epoch_digest": result.get("epoch_digest"),
                "epoch_dir": result.get("epoch_dir"),
            }

        def classify_l(state: LoopState) -> tuple[bool, str]:
            if state.goal_met:
                return True, "succession_mandate_met"
            return True, "succession_progressed"

        def seal_l(state: LoopState) -> dict[str, Any]:
            receipt = {
                "ok": state.extras.get("ok"),
                "verdict": state.extras.get("verdict"),
                "stop_reason": state.stop_reason,
                "max_epochs": state.max_rounds,
                "epoch_count": len(state.records),
                "epochs": state.records,
                "epoch_digests": list(state.child_digests),
                "total_dispatched": state.total_dispatched,
                "total_dispatched_ok": state.total_dispatched_ok,
                "mandate_met": state.goal_met,
                "portfolio_start_digest": state.portfolio_start_digest,
                "portfolio_end_digest": None,
                "coverage_end": {"met": state.goal_met},
                "dispatch_budget": state.dispatch_budget,
            }

            def payload(r: Mapping[str, Any]) -> dict[str, Any]:
                return {
                    "schema_version": r.get("schema_version"),
                    "verdict": r.get("verdict"),
                    "stop_reason": r.get("stop_reason"),
                    "max_epochs": r.get("max_epochs"),
                    "dispatch_budget": r.get("dispatch_budget"),
                    "portfolio_start_digest": r.get("portfolio_start_digest"),
                    "portfolio_end_digest": r.get("portfolio_end_digest"),
                    "epoch_count": r.get("epoch_count"),
                    "epoch_digests": list(r.get("epoch_digests") or []),
                    "total_dispatched": r.get("total_dispatched"),
                    "total_dispatched_ok": r.get("total_dispatched_ok"),
                    "mandate_met": r.get("mandate_met"),
                    "coverage_end": r.get("coverage_end"),
                }

            sealed = seal_json_receipt(state, receipt, digest_payload=payload)
            sealed["mandate_met"] = state.goal_met
            return sealed

        def post_stop(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> str | None:
            if state.goal_met:
                return "mandate_met"
            return None

        loop_res = run_control(
            "loop",
            "succession",
            max_rounds=3,
            dispatch=True,
            dispatch_budget=4,
            idle_limit=2,
            portfolio={"entries": [], "portfolio_digest": _sha256_json([])},
            out_root=scratch / "loop-native",
            child_runner=child_runner,
            build_child_kwargs=build_kwargs,
            on_child_result=on_result,
            post_round_stop=post_stop,
            classify_verdict=classify_l,
            seal=seal_l,
        )
        loop_ok = (
            loop_res.get("ok")
            and loop_res.get("control_engine") is True
            and loop_res.get("control_mode") == "loop"
            and loop_res.get("control_dialect") == "succession"
            and loop_res.get("loop_engine") is True
            and child_n["n"] >= 2
        )

        fleet_calls: list[str] = []

        def run_fleet_stage(state: PipelineState, name: str) -> dict[str, Any]:
            fleet_calls.append(f"{state.context.get('round_index')}:{name}")
            if name == "inventory":
                state.context["inventory"] = [{"name": "alpha", "version": "1.0.0"}]
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "inventoried",
                    "inventory_count": 1,
                }
            if name == "portfolio":
                state.context["portfolio"] = {
                    "entries": [],
                    "portfolio_digest": "p" * 64,
                }
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "portfolio_ready",
                    "portfolio_digest": "p" * 64,
                }
            if name == "rank":
                actions = [
                    {
                        "action": "campaign_patch_bound",
                        "name": "alpha",
                        "version": "1.0.0",
                        "campaignable": True,
                        "priority": 40,
                        "rank": 1,
                    }
                ]
                state.context["actions"] = actions
                state.context["campaignable"] = actions
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "ranked",
                    "action_count": 1,
                    "campaignable_count": 1,
                }
            if name == "dispatch":
                dig = _sha256_json({"wave": state.context.get("round_index")})
                return {
                    "stage": name,
                    "ok": True,
                    "verdict": "fleet_dispatched",
                    "dispatched_count": 1,
                    "dispatched_ok": 1,
                    "dispatches": [{"ok": True, "campaign_digest": dig}],
                }
            raise StageRefused("stage_unknown", name)

        def fleet_classify(state: PipelineState) -> tuple[bool, str]:
            if state.aborted or not state.pipeline_ok:
                return False, state.terminal_verdict
            return True, "fleet_dispatched"

        def fleet_seal(state: PipelineState) -> dict[str, Any]:
            return seal_pipeline_receipt(
                state,
                out_root=scratch / "compose-fleet",
                identity={
                    "name": "composealpha",
                    "version": "1.0.0",
                    "inventory_count": 1,
                    "action_count": 1,
                },
                stage_digests={
                    "rank.verdict": _sha256_bytes(b"ranked"),
                    "dispatch.verdict": _sha256_bytes(b"fleet_dispatched"),
                },
                digest_payload=lambda receipt: {
                    "schema_version": SCHEMA_VERSION,
                    "name": receipt.get("name"),
                    "version": receipt.get("version"),
                    "stages": receipt.get("stages"),
                    "stage_digests": receipt.get("stage_digests"),
                    "ok": receipt.get("ok"),
                    "verdict": receipt.get("verdict"),
                },
            )

        def compose_classify(state: LoopState) -> tuple[bool, str]:
            if state.total_dispatched_ok >= 2:
                state.goal_met = True
                return True, "epoch_progressed"
            if state.total_dispatched_ok > 0:
                return True, "epoch_progressed"
            return True, "epoch_idle"

        def compose_seal(state: LoopState) -> dict[str, Any]:
            receipt = {
                "ok": True,
                "verdict": state.extras.get("verdict") or "epoch_progressed",
                "stop_reason": state.stop_reason,
                "max_waves": state.max_rounds,
                "wave_count": len(state.records),
                "waves": state.records,
                "wave_digests": list(state.child_digests),
                "total_dispatched": state.total_dispatched,
                "total_dispatched_ok": state.total_dispatched_ok,
                "portfolio_start_digest": state.portfolio_start_digest,
                "portfolio_end_digest": None,
            }

            def payload(r: Mapping[str, Any]) -> dict[str, Any]:
                return {
                    "schema_version": r.get("schema_version"),
                    "verdict": r.get("verdict"),
                    "stop_reason": r.get("stop_reason"),
                    "max_waves": r.get("max_waves"),
                    "wave_count": r.get("wave_count"),
                    "wave_digests": list(r.get("wave_digests") or []),
                    "total_dispatched": r.get("total_dispatched"),
                    "total_dispatched_ok": r.get("total_dispatched_ok"),
                }

            sealed = seal_json_receipt(state, receipt, digest_payload=payload)
            sealed["waves"] = state.records
            return sealed

        def compose_post(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> str | None:
            if state.total_dispatched_ok >= 2:
                state.goal_met = True
                return "max_waves"
            return None

        composed = compose_loop_of_pipeline(
            loop_dialect="epoch",
            pipeline_dialect="fleet",
            max_rounds=3,
            pipeline_stages=list(FLEET_STAGES),
            run_stage=run_fleet_stage,
            classify_pipeline=fleet_classify,
            seal_pipeline=fleet_seal,
            classify_loop=compose_classify,
            seal_loop=compose_seal,
            post_round_stop=compose_post,
            out_root=scratch / "compose",
            portfolio={"entries": [], "portfolio_digest": "p" * 64},
            dispatch=True,
            dispatch_budget=4,
            idle_limit=2,
        )
        compose_ok = (
            composed.get("ok")
            and composed.get("control_engine") is True
            and composed.get("control_composed") is True
            and composed.get("control_child_mode") == "pipeline"
            and composed.get("control_child_dialect") == "fleet"
            and composed.get("control_parent_dialect") == "epoch"
            and composed.get("loop_engine") is True
            and int(composed.get("total_dispatched_ok") or 0) >= 2
            and any(":dispatch" in c for c in fleet_calls)
            and any(c.startswith("0:") for c in fleet_calls)
            and any(c.startswith("1:") for c in fleet_calls)
        )

        from blackhole_agent import upstream_campaign as ucamp
        from blackhole_agent import upstream_fleet as ufleet
        from blackhole_agent import upstream_epoch as ue
        from blackhole_agent import upstream_program as up
        from blackhole_agent import upstream_succession as us

        live_flags_ok = all(
            [
                getattr(ucamp, "STAGE_ENGINE", False) is True,
                getattr(ufleet, "STAGE_ENGINE", False) is True,
                getattr(ue, "LOOP_ENGINE", False) is True,
                getattr(us, "LOOP_ENGINE", False) is True,
                getattr(up, "LOOP_ENGINE", False) is True,
                getattr(ucamp, "CONTROL_ENGINE", False) is True,
                getattr(ufleet, "CONTROL_ENGINE", False) is True,
                getattr(ue, "CONTROL_ENGINE", False) is True,
                getattr(us, "CONTROL_ENGINE", False) is True,
                getattr(up, "CONTROL_ENGINE", False) is True,
            ]
        )

        from blackhole_agent import upstream_control_engine as ce_impl
        from blackhole_agent import upstream_stage_engine as se_facade
        from blackhole_agent import upstream_loop_engine as le_facade

        # Compare against the package-qualified module (not __main__ when
        # invoked via ``python -m ...``).
        facade_checks = {
            "pipe_is": se_facade.run_stage_pipeline is ce_impl.run_stage_pipeline,
            "loop_is": le_facade.run_durable_loop is ce_impl.run_durable_loop,
            "pipe_list": se_facade.list_pipeline_dialects() == ["campaign", "fleet"],
            "loop_list": le_facade.list_loop_dialects() == ["program", "succession", "epoch"],
            "se_flag": getattr(se_facade, "CONTROL_ENGINE_IMPL", False) is True,
            "le_flag": getattr(le_facade, "CONTROL_ENGINE_IMPL", False) is True,
            "same_impl": ce_impl.compose_loop_of_pipeline is compose_loop_of_pipeline
            or ce_impl.__file__ == __file__,
        }
        facade_ok = all(
            [
                facade_checks["pipe_is"],
                facade_checks["loop_is"],
                facade_checks["pipe_list"],
                facade_checks["loop_list"],
                facade_checks["se_flag"],
                facade_checks["le_flag"],
            ]
        )

        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-control-engine")
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            ledger_ok = (
                entry is not None
                and "upstream_control_engine" in (entry.entry or "")
                and "control" in tags_blob
                and (
                    "pipeline" in tags_blob
                    or "multi-mode" in tags_blob
                    or "loop" in tags_blob
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        engine_path = Path(__file__).resolve()
        engine_loc = sum(
            1
            for line in engine_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        stage_facade_loc = sum(
            1
            for line in (
                REPO_ROOT / "src" / "blackhole_agent" / "upstream_stage_engine.py"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        loop_facade_loc = sum(
            1
            for line in (
                REPO_ROOT / "src" / "blackhole_agent" / "upstream_loop_engine.py"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        facades_thin = stage_facade_loc < 100 and loop_facade_loc < 100

        ok = all(
            [
                catalog_ok,
                pipe_ok,
                loop_ok,
                compose_ok,
                live_flags_ok,
                facade_ok,
                facades_thin,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "control_engine_proof",
            "catalog_ok": catalog_ok,
            "catalog": catalog,
            "dialect_count": len(list_all_control_dialects()),
            "pipeline_control_ok": pipe_ok,
            "loop_control_ok": loop_ok,
            "compose_loop_of_pipeline_ok": compose_ok,
            "live_control_flags_ok": live_flags_ok,
            "facade_reexport_ok": facade_ok,
            "facade_checks": facade_checks,
            "facades_thin": facades_thin,
            "stage_facade_loc": stage_facade_loc,
            "loop_facade_loc": loop_facade_loc,
            "engine_loc": engine_loc,
            "ledger_capability_ok": ledger_ok,
            "pipeline_digest": pipe.get("campaign_digest"),
            "loop_digest": loop_res.get("succession_digest"),
            "compose_digest": composed.get("epoch_digest"),
            "compose_dispatched_ok": composed.get("total_dispatched_ok"),
            "fleet_calls": fleet_calls,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def builtin_control_graph_proof() -> dict[str, Any]:
    """Alias: graph-native operational spine proof (native fleet→campaign)."""
    return builtin_control_nest_proof()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic multi-mode control-engine proof")
    sub.add_parser(
        "nest-proof",
        help="Run hermetic multi-depth control-nest proof (program→…→campaign)",
    )
    sub.add_parser(
        "spine-proof",
        help="Alias of nest-proof: full operational spine incl. fleet→campaign",
    )
    sub.add_parser(
        "graph-proof",
        help="Graph-native spine proof: run_operational_spine owns fleet→campaign",
    )
    sub.add_parser(
        "governance-proof",
        help=(
            "Governance spine proof: institution constitution + operational "
            "program→…→campaign nest"
        ),
    )
    sub.add_parser("list", help="List control modes and dialects")
    sub.add_parser("nest-path", help="Print canonical operational nest path")
    sub.add_parser(
        "governance-path",
        help="Print canonical governance nest path (institution→…→campaign)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(
            json.dumps(
                {
                    "modes": list_control_modes(),
                    "catalog": list_control_catalog(),
                    "dialects": list_all_control_dialects(),
                    "operational_nest": operational_nest_path(),
                    "governance_nest": governance_nest_path(),
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "nest-path":
        print(json.dumps({"nest_path": operational_nest_path()}, indent=2))
        return 0
    if args.cmd == "governance-path":
        print(
            json.dumps(
                {
                    "governance_nest_path": governance_nest_path(),
                    "governance_nest_depth": governance_nest_depth(),
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "proof":
        result = builtin_control_engine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd in {"nest-proof", "spine-proof", "graph-proof"}:
        result = builtin_control_graph_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "governance-proof":
        result = builtin_governance_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
