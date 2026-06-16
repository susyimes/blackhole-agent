"""LLM-assisted proposal synthesis with deterministic review gates."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROPOSAL_SYNTHESIS_SCHEMA_VERSION = 1
PROPOSAL_MODES = {"heuristic", "llm", "hybrid"}
DEFAULT_PROPOSAL_MODE = "hybrid"
DEFAULT_MAX_ITEM_TEXT_CHARS = 1200
ALLOWED_PROPOSAL_KINDS = {"documentation", "test", "code_patch", "config", "follow_up_issue", "no_action"}
ALLOWED_IMPLEMENTATION_SCOPES = {
    "local_validation_candidate",
    "risk_review_before_local_change",
    "reviewable_proposal_only",
}
HIGH_RISK_FLAGS = {
    "offensive-behavior",
    "privacy-leakage",
}
FORBIDDEN_ACTION_TERMS = (
    "attack",
    "backdoor",
    "credential stuffing",
    "ddos",
    "denial of service",
    "dump api key",
    "dump credentials",
    "dump private key",
    "dump secret",
    "dump token",
    "expose api key",
    "expose credentials",
    "expose private key",
    "expose secret",
    "expose token",
    "exfiltrate",
    "exploit",
    "log api key",
    "log credentials",
    "log private key",
    "log secret",
    "log token",
    "leak token",
    "malware",
    "phishing",
    "print api key",
    "print credentials",
    "print private key",
    "print secret",
    "print token",
    "publish api key",
    "publish credentials",
    "publish private key",
    "publish secret",
    "publish token",
    "ransomware",
    "share api key",
    "share credentials",
    "share private key",
    "share secret",
    "share token",
    "upload api key",
    "upload credentials",
    "upload private key",
    "upload secret",
    "upload token",
)


@dataclass(frozen=True)
class ProposalSynthesisReview:
    """Review outcome for an LLM proposal synthesis attempt."""

    schema_version: int
    mode: str
    status: str
    reason: str
    input_digest_id: str
    input_hash: str
    output_hash: str
    accepted_count: int
    rejected_count: int
    accepted_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    interpretation: dict[str, Any]
    self_model_reading: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "status": self.status,
            "reason": self.reason,
            "input_digest_id": self.input_digest_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "accepted_candidates": self.accepted_candidates,
            "rejected_candidates": self.rejected_candidates,
            "interpretation": self.interpretation,
            "self_model_reading": self.self_model_reading,
        }


def validate_proposal_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in PROPOSAL_MODES:
        raise ValueError("proposal_mode must be one of: heuristic, llm, hybrid")
    return normalized


def build_proposal_evidence_package(
    digest: dict[str, Any],
    *,
    self_model_snapshot: dict[str, Any] | None = None,
    max_items: int = 20,
    max_item_text_chars: int = DEFAULT_MAX_ITEM_TEXT_CHARS,
    max_self_model_chars: int = 4000,
) -> dict[str, Any]:
    """Build the frozen input package an LLM may interpret."""

    items: list[dict[str, Any]] = []
    allowed_urls: list[str] = []
    all_digest_items = digest.get("items", [])
    digest_items = all_digest_items[:max_items] if isinstance(all_digest_items, list) else []
    item_truncation: list[dict[str, Any]] = []
    for index, item in enumerate(digest_items, start=1):
        item_id = str(item.get("item_id") or f"item-{index}")
        source_url = str(item.get("source_url") or "")
        if source_url:
            allowed_urls.append(source_url)
        summary, summary_meta = truncate_text(str(item.get("summary") or ""), max_item_text_chars)
        relevance_reason, relevance_meta = truncate_text(
            str(item.get("relevance_reason") or ""),
            max_item_text_chars,
        )
        truncated_fields = []
        if summary_meta["truncated"]:
            truncated_fields.append({"field": "summary", **summary_meta})
        if relevance_meta["truncated"]:
            truncated_fields.append({"field": "relevance_reason", **relevance_meta})
        if truncated_fields:
            item_truncation.append({"item_id": item_id, "fields": truncated_fields})
        items.append(
            {
                "item_id": item_id,
                "source_url": source_url,
                "event_kind": str(item.get("event_kind") or ""),
                "summary": summary,
                "relevance_reason": relevance_reason,
                "rule_risk_flags": [str(flag) for flag in item.get("risk_flags", [])],
                "rule_confidence": float(item.get("confidence") or 0.0),
            }
        )
    snapshot = self_model_snapshot or {}
    self_model_content, self_model_truncation = truncate_text(
        str(snapshot.get("content") or ""),
        max_self_model_chars,
    )
    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "digest_id": str(digest.get("digest_id") or ""),
        "generated_at": str(digest.get("generated_at") or ""),
        "allowed_evidence_urls": sorted(set(allowed_urls)),
        "items": items,
        "context_budget": {
            "max_items": max_items,
            "input_item_count": len(all_digest_items) if isinstance(all_digest_items, list) else 0,
            "items_truncated": isinstance(all_digest_items, list) and len(all_digest_items) > max_items,
            "max_item_text_chars": max_item_text_chars,
            "item_text_truncation": item_truncation,
        },
        "self_model": {
            "path": str(snapshot.get("path") or ""),
            "sha256": str(snapshot.get("sha256") or ""),
            "content": self_model_content,
            "truncated": bool(snapshot.get("truncated") or False) or self_model_truncation["truncated"],
            "content_original_chars": self_model_truncation["original_chars"],
            "content_kept_chars": self_model_truncation["kept_chars"],
        },
        "policy": {
            "allowed_kinds": sorted(ALLOWED_PROPOSAL_KINDS),
            "allowed_scopes": sorted(ALLOWED_IMPLEMENTATION_SCOPES),
            "max_proposals": 5,
            "evidence_refs_must_point_to_items": True,
            "final_scope_and_gate_are_recomputed_by_controller": True,
            "safety_boundary": {
                "review_only": ["offensive-behavior", "privacy-leakage"],
                "allowed_when_locally_validated": [
                    "controller internals",
                    "runtime behavior",
                    "provider/config preflight",
                    "runner and remote-execution plumbing",
                    "tool routing",
                    "scheduling",
                    "memory",
                    "tests",
                    "documentation",
                ],
            },
        },
    }


def build_context_budget_preflight(evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Summarize proposal context pressure without exposing evidence content or URLs."""

    context_budget = evidence_package.get("context_budget") if isinstance(evidence_package, dict) else {}
    context_budget = context_budget if isinstance(context_budget, dict) else {}
    items = evidence_package.get("items") if isinstance(evidence_package, dict) else []
    items = items if isinstance(items, list) else []
    item_text_truncation = context_budget.get("item_text_truncation")
    item_text_truncation = item_text_truncation if isinstance(item_text_truncation, list) else []
    truncated_field_count = 0
    for entry in item_text_truncation:
        if isinstance(entry, dict) and isinstance(entry.get("fields"), list):
            truncated_field_count += len(entry["fields"])
    self_model = evidence_package.get("self_model") if isinstance(evidence_package, dict) else {}
    self_model = self_model if isinstance(self_model, dict) else {}
    items_truncated = bool(context_budget.get("items_truncated"))
    text_truncated = bool(item_text_truncation)
    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "digest_id": str(evidence_package.get("digest_id") or "") if isinstance(evidence_package, dict) else "",
        "generated_at": str(evidence_package.get("generated_at") or "") if isinstance(evidence_package, dict) else "",
        "input_hash": stable_hash(evidence_package) if isinstance(evidence_package, dict) else "",
        "status": "pressure_detected" if items_truncated or text_truncated else "within_budget",
        "local_metadata_only": True,
        "external_fetch_performed": False,
        "max_items": int(context_budget.get("max_items") or 0),
        "input_item_count": int(context_budget.get("input_item_count") or 0),
        "kept_item_count": len(items),
        "items_truncated": items_truncated,
        "max_item_text_chars": int(context_budget.get("max_item_text_chars") or 0),
        "truncated_item_count": len(item_text_truncation),
        "truncated_field_count": truncated_field_count,
        "self_model_truncated": bool(self_model.get("truncated")),
    }


def truncate_text(value: str, limit: int) -> tuple[str, dict[str, int | bool]]:
    """Return a deterministic character-bounded copy plus replay metadata."""

    normalized_limit = max(0, int(limit))
    truncated = len(value) > normalized_limit
    return value[:normalized_limit], {
        "truncated": truncated,
        "original_chars": len(value),
        "kept_chars": min(len(value), normalized_limit),
    }


def render_proposal_synthesis_prompt(evidence_package: dict[str, Any]) -> str:
    """Render a read-only prompt that asks for route interpretation, not mutation."""

    return "\n".join(
        [
            "You are the read-only proposal interpretation layer for blackhole-agent.",
            "",
            "Your job is to interpret frozen evidence and propose growth routes as strict JSON.",
            "Do not edit files. Do not run broad searches. Do not add evidence URLs.",
            "Runtime permissions, final implementation scope, validation gates, and approval are recomputed by code.",
            "The safety boundary is narrow: only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only.",
            "Provider/config/token preflight, runners, tool routing, scheduling, memory, tests, and controller behavior are allowed routes when locally validated.",
            "",
            "Return only a JSON object with:",
            "- schema_version: 1",
            "- input_digest_id",
            "- run_interpretation: string",
            "- self_model_reading: object",
            "- proposals: array of proposal candidates",
            "- rejected_items: array",
            "",
            "Each proposal candidate must include:",
            "proposal_id, kind, summary, evidence_refs, added_risk_flags, validation_task, rationale, uncertainty,",
            "self_effect, and action_lane.",
            "",
            "Frozen evidence package:",
            "```json",
            json.dumps(evidence_package, indent=2, sort_keys=True),
            "```",
        ]
    )


def review_llm_proposal_response(
    raw_text: str,
    evidence_package: dict[str, Any],
    *,
    mode: str,
) -> ProposalSynthesisReview:
    """Validate an LLM response and return accepted candidates plus replay metadata."""

    normalized_mode = validate_proposal_mode(mode)
    input_digest_id = str(evidence_package.get("digest_id") or "")
    input_hash = stable_hash(evidence_package)
    output_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    try:
        payload = extract_json_object(raw_text)
    except ValueError as error:
        return rejected_review(
            mode=normalized_mode,
            reason=str(error),
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    if int(payload.get("schema_version") or 0) != PROPOSAL_SYNTHESIS_SCHEMA_VERSION:
        return rejected_review(
            mode=normalized_mode,
            reason="schema_version must be 1",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )
    if str(payload.get("input_digest_id") or "") != input_digest_id:
        return rejected_review(
            mode=normalized_mode,
            reason="input_digest_id does not match evidence package",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    items_by_id = {str(item.get("item_id")): item for item in evidence_package.get("items", [])}
    max_proposals = int(evidence_package.get("policy", {}).get("max_proposals") or 5)
    candidates = payload.get("proposals")
    if not isinstance(candidates, list):
        return rejected_review(
            mode=normalized_mode,
            reason="proposals must be a list",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )
    if len(candidates) > max_proposals:
        return rejected_review(
            mode=normalized_mode,
            reason=f"proposal count exceeds max_proposals={max_proposals}",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        normalized, errors = normalize_candidate(candidate, items_by_id, index=index)
        if errors:
            rejected.append({"candidate": candidate, "errors": errors})
        else:
            accepted.append(normalized)
    status = "accepted" if accepted else "rejected"
    reason = "accepted" if accepted else "no valid proposals"
    return ProposalSynthesisReview(
        schema_version=PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        mode=normalized_mode,
        status=status,
        reason=reason,
        input_digest_id=input_digest_id,
        input_hash=input_hash,
        output_hash=output_hash,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        accepted_candidates=accepted,
        rejected_candidates=rejected,
        interpretation={
            "run_interpretation": str(payload.get("run_interpretation") or ""),
            "rejected_items": payload.get("rejected_items") if isinstance(payload.get("rejected_items"), list) else [],
        },
        self_model_reading=payload.get("self_model_reading")
        if isinstance(payload.get("self_model_reading"), dict)
        else {},
    )


def normalize_candidate(
    candidate: Any,
    items_by_id: dict[str, dict[str, Any]],
    *,
    index: int,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(candidate, dict):
        return {}, ["candidate must be an object"]
    errors: list[str] = []
    kind = str(candidate.get("kind") or "")
    if kind not in ALLOWED_PROPOSAL_KINDS:
        errors.append("kind is not allowed")
    evidence_refs = [str(ref) for ref in candidate.get("evidence_refs", []) if str(ref).strip()]
    if not evidence_refs:
        errors.append("evidence_refs must not be empty")
    supplied_evidence_urls = [str(url) for url in candidate.get("evidence_urls", []) if str(url).strip()]
    if supplied_evidence_urls:
        errors.append("evidence_urls must be derived from frozen evidence_refs, not supplied by candidates")
    missing_refs = [ref for ref in evidence_refs if ref not in items_by_id]
    if missing_refs:
        errors.append("evidence_refs contain unknown item ids: " + ", ".join(missing_refs))
    validation_task = str(candidate.get("validation_task") or "").strip()
    if not validation_task:
        errors.append("validation_task must not be empty")
    dangerous_text = " ".join(
        str(candidate.get(key) or "") for key in ("summary", "validation_task", "rationale", "self_effect")
    ).lower()
    forbidden = [term for term in FORBIDDEN_ACTION_TERMS if term in dangerous_text]
    validation_lower = validation_task.lower()
    if (
        forbidden
        and "risk_review" not in validation_lower
        and "review" not in validation_lower
        and "validate" not in validation_lower
    ):
        errors.append("dangerous action language must be framed as review or validation")
    added_flags = [str(flag) for flag in candidate.get("added_risk_flags", []) if str(flag).strip()]
    rule_flags = sorted(
        {
            str(flag)
            for ref in evidence_refs
            for flag in items_by_id.get(ref, {}).get("rule_risk_flags", [])
            if str(flag).strip()
        }
    )
    normalized = {
        "proposal_id": str(candidate.get("proposal_id") or f"llm-{index}"),
        "kind": kind,
        "summary": str(candidate.get("summary") or "").strip(),
        "evidence_refs": evidence_refs,
        "evidence_urls": sorted(
            {
                str(items_by_id[ref].get("source_url") or "")
                for ref in evidence_refs
                if ref in items_by_id and str(items_by_id[ref].get("source_url") or "").strip()
            }
        ),
        "rule_risk_flags": rule_flags,
        "added_risk_flags": sorted(set(added_flags)),
        "validation_task": validation_task,
        "rationale": str(candidate.get("rationale") or "").strip(),
        "uncertainty": str(candidate.get("uncertainty") or "").strip(),
        "self_effect": str(candidate.get("self_effect") or "").strip(),
        "action_lane": str(candidate.get("action_lane") or "").strip(),
    }
    return normalized, errors


def rejected_review(
    *,
    mode: str,
    reason: str,
    input_digest_id: str,
    input_hash: str,
    output_hash: str,
) -> ProposalSynthesisReview:
    return ProposalSynthesisReview(
        schema_version=PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        mode=mode,
        status="rejected",
        reason=reason,
        input_digest_id=input_digest_id,
        input_hash=input_hash,
        output_hash=output_hash,
        accepted_count=0,
        rejected_count=0,
        accepted_candidates=[],
        rejected_candidates=[],
        interpretation={},
        self_model_reading={},
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(f"LLM proposal response was not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("LLM proposal response must be a JSON object")
    return payload


def write_proposal_synthesis_artifacts(
    output_dir: Path,
    *,
    evidence_package: dict[str, Any],
    review: ProposalSynthesisReview,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_text = json.dumps(evidence_package, indent=2, sort_keys=True) + "\n"
    review_text = json.dumps(review.to_dict(), indent=2, sort_keys=True) + "\n"
    (output_dir / f"proposal-evidence-package-{timestamp}.json").write_text(evidence_text, encoding="utf-8")
    (output_dir / f"llm-proposal-review-{timestamp}.json").write_text(review_text, encoding="utf-8")
    (output_dir / "latest-proposal-evidence-package.json").write_text(evidence_text, encoding="utf-8")
    (output_dir / "latest-llm-proposal-review.json").write_text(review_text, encoding="utf-8")
    interpretation_text = json.dumps(review.interpretation, indent=2, sort_keys=True) + "\n"
    self_model_text = json.dumps(review.self_model_reading, indent=2, sort_keys=True) + "\n"
    (output_dir / "latest-growth-interpretation.json").write_text(interpretation_text, encoding="utf-8")
    (output_dir / "latest-self-model-reading.json").write_text(self_model_text, encoding="utf-8")


def write_context_budget_preflight_artifact(output_dir: Path, *, evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Persist the local context-budget preflight before proposal interpretation runs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    preflight = build_context_budget_preflight(evidence_package)
    preflight_text = json.dumps(preflight, indent=2, sort_keys=True) + "\n"
    (output_dir / f"context-budget-preflight-{timestamp}.json").write_text(preflight_text, encoding="utf-8")
    (output_dir / "latest-context-budget-preflight.json").write_text(preflight_text, encoding="utf-8")
    return preflight


def stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
