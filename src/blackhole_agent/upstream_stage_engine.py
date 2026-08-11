"""Generic multi-stage durable pipeline engine for operational stewardship.

Collapses the campaign plane's hand-wired stage if-chain
(discovery → admit → repair → contribution → publication → impact) into one
noun-parameterized control-flow engine:

1. validate ordered stage list against a pipeline dialect
2. run each selected stage through an injected runner
3. short-circuit on abortable failure (or continue when dialect allows)
4. let dialect hooks mutate shared pipeline context between stages
5. classify terminal verdict + seal a digest-chained pipeline receipt

Stage *domain logic* stays in ``upstream_campaign`` / plane modules. This
engine owns *orchestration control flow* the same way
``upstream_loop_engine`` owns multi-round loops and
``upstream_constitution_engine`` owns multi-child constitutions.

New operational pipelines are a :class:`PipelineDialect` row plus stage
hooks — not another ~1600-line hand-wired stage sequencer.
No skill-route discovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


# Registered operational pipelines (campaign is the primary dialect).
CAMPAIGN_STAGES: tuple[str, ...] = (
    "discovery",
    "admit",
    "repair",
    "contribution",
    "publication",
    "impact",
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
)

PIPELINE_DIALECTS: dict[str, PipelineDialect] = {d.name: d for d in PIPELINE_STACK}


def get_pipeline_dialect(name: str) -> PipelineDialect:
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
    """Hermetic proof that the stage engine owns campaign pipeline control flow.

    Proves:
    - pipeline dialect registration
    - engine-native multi-stage run with abort-on-fail and soft-fail
    - digest seal + tamper detection
    - live ``upstream_campaign.run_campaign`` sets stage_engine ownership
    - live campaign builtin proof stays green
    - ledger binding for capability.upstream-stage-engine
    - no skill-route discovery
    """
    scratch = Path(tempfile.mkdtemp(prefix="stage-engine-proof-"))
    try:
        dialects = list_pipeline_dialects()
        dialects_ok = dialects == ["campaign"] and "campaign" in PIPELINE_DIALECTS
        campaign_d = get_pipeline_dialect("campaign")
        known_stages_ok = set(CAMPAIGN_STAGES) == set(campaign_d.valid_stages)

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

        # Unknown stages refused.
        unknown_refused = False
        try:
            normalize_stages("campaign", ("repair", "not_a_stage"))
        except StageRefused as exc:
            unknown_refused = exc.verdict == "stages_unknown"

        # Live campaign module ownership.
        from blackhole_agent import upstream_campaign as ucamp

        campaign_uses_engine = getattr(ucamp, "STAGE_ENGINE", False) is True
        campaign_dialect = getattr(ucamp, "STAGE_ENGINE_DIALECT", "") == "campaign"

        # Re-prove live campaign (must stay green after migration).
        live_proof = ucamp.builtin_upstream_campaign_proof()
        live_proof_ok = bool(live_proof.get("ok"))

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
            ledger_ok = (
                entry is not None
                and "upstream_stage_engine" in (entry.entry or "")
                and "stage" in " ".join(entry.tags).lower()
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
                campaign_uses_engine,
                campaign_dialect,
                live_flag,
                live_digest_present,
                live_proof_ok,
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
            "unknown_stages_refused": unknown_refused,
            "campaign_stage_engine": campaign_uses_engine,
            "campaign_stage_engine_dialect": campaign_dialect,
            "live_campaign_flag": live_flag,
            "live_campaign_digest": live_digest_present,
            "live_campaign_proof_ok": live_proof_ok,
            "live_exc": live_exc,
            "ledger_capability_ok": ledger_ok,
            "engine_loc": engine_loc,
            "campaign_loc": campaign_loc,
            "engine_native_digest": full.get("campaign_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic stage-engine proof")
    sub.add_parser("list", help="List registered pipeline dialects")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(json.dumps({"dialects": list_pipeline_dialects()}, indent=2))
        return 0
    if args.cmd == "proof":
        result = builtin_stage_engine_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
