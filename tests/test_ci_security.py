from blackhole_agent.ci_security import SecurityScanGateInput, evaluate_security_scan_gate


def test_security_scan_success_allows_without_waiver_label():
    decision = evaluate_security_scan_gate(SecurityScanGateInput(scan_conclusion="success", pull_request_labels=()))

    assert decision.allowed is True
    assert decision.waiver_applied is False
    assert decision.outcome == "security_scan_passed"


def test_failed_security_scan_requires_exact_label_only_waiver():
    decision = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="failure",
            pull_request_labels=("security-scan-waiver",),
            current_run_attempt=2,
            label_snapshot_run_attempt=2,
        )
    )

    assert decision.allowed is True
    assert decision.waiver_applied is True
    assert decision.outcome == "waiver_label_applied"
    assert "label_only_waiver_present" in decision.reasons


def test_failed_security_scan_blocks_without_waiver_label():
    decision = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="failure",
            pull_request_labels=("needs-review", "safe-to-test"),
            current_run_attempt=2,
            label_snapshot_run_attempt=2,
        )
    )

    assert decision.allowed is False
    assert decision.waiver_applied is False
    assert decision.outcome == "security_scan_blocked"
    assert "missing_waiver_label" in decision.reasons


def test_rerun_cannot_reuse_stale_label_snapshot_to_bypass_scan():
    decision = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="failure",
            pull_request_labels=("security-scan-waiver",),
            current_run_attempt=3,
            label_snapshot_run_attempt=2,
        )
    )

    assert decision.allowed is False
    assert decision.waiver_applied is False
    assert "stale_label_snapshot_for_rerun" in decision.reasons


def test_missing_rerun_label_snapshot_blocks_waiver_path():
    decision = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="timed_out",
            pull_request_labels=("SECURITY-SCAN-WAIVER",),
            current_run_attempt=4,
            label_snapshot_run_attempt=None,
        )
    )

    assert decision.allowed is False
    assert "missing_label_snapshot_run_attempt" in decision.reasons
