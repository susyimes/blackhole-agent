"""Local CI security gate models used for offline validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


SECURITY_SCAN_WAIVER_LABEL = "security-scan-waiver"
SECURITY_SCAN_SUCCESS_CONCLUSIONS = frozenset({"success"})


@dataclass(frozen=True)
class SecurityScanGateInput:
    """Metadata-only state for a security-scan gate decision.

    The waiver path is intentionally label-only. It does not inspect comments,
    commit messages, workflow inputs, environment variables, or secret values.
    """

    scan_conclusion: str | None
    pull_request_labels: tuple[str, ...] = ()
    current_run_attempt: int = 1
    label_snapshot_run_attempt: int | None = 1
    waiver_label: str = SECURITY_SCAN_WAIVER_LABEL


@dataclass(frozen=True)
class SecurityScanGateDecision:
    """Inspectable result for a local security-scan waiver simulation."""

    allowed: bool
    outcome: str
    reasons: tuple[str, ...]
    waiver_applied: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "waiver_applied": self.waiver_applied,
        }


def evaluate_security_scan_gate(state: SecurityScanGateInput) -> SecurityScanGateDecision:
    """Evaluate a fail-closed security-scan gate from PR metadata only."""

    conclusion = normalize_label(state.scan_conclusion)
    if conclusion in SECURITY_SCAN_SUCCESS_CONCLUSIONS:
        return SecurityScanGateDecision(
            allowed=True,
            outcome="security_scan_passed",
            reasons=("scan_conclusion:success",),
        )

    reasons = [f"scan_conclusion:{conclusion or 'missing'}"]
    if state.current_run_attempt < 1:
        reasons.append("invalid_current_run_attempt")
    if state.label_snapshot_run_attempt is None:
        reasons.append("missing_label_snapshot_run_attempt")
    elif state.label_snapshot_run_attempt != state.current_run_attempt:
        reasons.append("stale_label_snapshot_for_rerun")

    waiver_present = has_label(state.pull_request_labels, state.waiver_label)
    if not waiver_present:
        reasons.append("missing_waiver_label")
    if not state.waiver_label.strip():
        reasons.append("empty_waiver_label")

    waiver_allowed = (
        waiver_present
        and bool(state.waiver_label.strip())
        and state.current_run_attempt >= 1
        and state.label_snapshot_run_attempt == state.current_run_attempt
    )
    if waiver_allowed:
        return SecurityScanGateDecision(
            allowed=True,
            outcome="waiver_label_applied",
            reasons=tuple(reasons + ["label_only_waiver_present"]),
            waiver_applied=True,
        )
    return SecurityScanGateDecision(
        allowed=False,
        outcome="security_scan_blocked",
        reasons=tuple(reasons),
    )


def has_label(labels: Sequence[str], expected: str) -> bool:
    """Return whether a GitHub label list contains the expected label."""

    expected_label = normalize_label(expected)
    return bool(expected_label) and expected_label in {normalize_label(label) for label in labels}


def normalize_label(value: str | None) -> str:
    return str(value or "").strip().casefold()
