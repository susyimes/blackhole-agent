from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_upstream_evidence_interpretation_doc_records_local_validation_contract():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")

    required_phrases = [
        "not direct\npermission",
        "bounded local validation candidate",
        "cite only URLs or item IDs present in the frozen digest evidence package",
        "missing implementation detail",
        "Low-detail upstream movement is a prompt for bounded validation",
        "Untitled pull requests, repeated generic PR lifecycle\nevents, generic push events",
        "should not justify `code_patch` work",
        "inspected PR body, commit diff, release\nnote, failing local test",
        "must\nnot add evidence URLs",
        "documentation",
        "test",
        "code patch",
        "config",
        "follow-up issue",
        "offensive behavior, abuse, unauthorized access, or privacy\nleakage remain review-only",
        "https://github.com/omnigent-ai/omnigent",
        "policies, sandboxing, spend limits",
        "low-detail movement around Omnigent PRs and\npushes",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_upstream_evidence_interpretation_doc_records_omnigent_watchlist_contract():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")

    required_phrases = [
        "## Omnigent Upstream Movement Watchlist",
        "Source digest: `github-growth-20260618T175207.227269Z`",
        "controller, runner, harness,\nand review workflow movement",
        "High-detail signals are actionable only as bounded local validation candidates",
        "`HarnessDescriptor`, `NativeServerHarness`, native\n  server transport",
        "allowlist-gated runtime\n  overrides, fail-closed permission decisions",
        "conformance parity,\n  transport contracts, permission mapping",
        "Weak signals are activity evidence, not implementation evidence",
        "untitled pull request metadata",
        "review anchors where GitHub exposes only \"left review comments\", \"found\n  potential problems\", \"fixed\"",
        "large size labels by themselves",
        "compare the proposed behavior with this repository's current controller,\n  runner, tool-routing, provider-preflight, and harness-validation contracts",
        "remote execution, credential access, promotion, push, restart, cloud\n  sandbox",
        "https://github.com/omnigent-ai/omnigent/pull/576#pullrequestreview-4527267074",
        "permission-policy fail-closed fixes",
        "not enough to copy a\n  patch without inspecting the specific finding or proving the local boundary",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_architecture_links_upstream_evidence_interpretation_contract():
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "docs/upstream-evidence-interpretation.md" in architecture
    assert "not permission or implementation authority" in architecture
    assert "low-detail PR/push interpretation rule" in architecture
    assert "docs/skill-route-discovery.md" in architecture
    assert "evolution_route" in architecture
    assert "blackhole_agent.evolution_route" in architecture
    assert "ledger_not_ready" in architecture
    assert "grow_capability_ledger_first" in architecture
    assert "capabilities/ledger.json" in architecture
    assert "provider_config_preflight" in architecture
    assert "governance_policy" in architecture
    assert "harness_activation_gate_decision" in architecture
    assert "uv run pytest" in architecture
    assert "uv run ruff check ." in architecture
    assert "uv run python -m blackhole_agent.size_ratchet" in architecture
    assert "protected governance paths" in architecture
    assert "pattern register" in architecture
    # The demolished labyrinth must not reappear as living architecture.
    assert architecture.count("skill_route_discovery_capability_pipeline") <= 1
    assert "pytest tests/test_harness_eval.py" not in architecture
    assert "pytest tests/test_skill_routing.py" not in architecture


def test_skill_route_discovery_doc_is_a_demolition_tombstone():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    assert "removed" in doc
    assert "src/blackhole_agent/skill_routing.py" in doc
    assert "src/blackhole_agent/harness_eval.py" in doc
    assert "are deleted" in doc
    assert "evolution_route" in doc
    assert "provider_config_preflight" in doc
    assert "governance_policy" in doc
    assert "harness_activation_gate_decision" in doc
    assert "capabilities/ledger.json" in doc


def test_upstream_evidence_interpretation_doc_records_capability_step_contract():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")

    required_phrases = [
        "## Upstream Evidence Capability Step",
        "Source digest: `github-growth-20260712T173308.992902Z`",
        "`upstream_evidence_capability_step`",
        "`privacy_boundary_review_only`",
        "`local_pr_compare_before_draft`",
        "`compare_pull_request_approach_with_local_agent_behavior_before_draft`",
        "pytest tests/test_github_growth.py -q -k upstream_evidence_capability_step",
        "raw evidence URLs and upstream bodies stay out of",
        "the packet",
        "## Agent Harness Eval Cluster",
        "Source digest: `github-growth-20260712T175313.658382Z`",
        "`agent_harness_eval_cluster`",
        "`prop-agent-harness-eval-cluster`",
        "evaluation_lane=agent_harness_eval_required",
        "local_validation_required=true",
        "Star count, trend rank, or popularity alone never unlocks",
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster",
        "## Agent Harness Eval Cluster Local Apply",
        "Source digest: `github-growth-20260712T181308.938536Z`",
        "`agent_harness_eval_cluster_local_apply`",
        "`apply_one_local_validation_candidate`",
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply",
        "## Agent Harness Eval Cluster Local Apply Completion",
        "Source digest: `github-growth-20260712T183309.245000Z`",
        "`agent_harness_eval_cluster_local_apply_completion`",
        "`prop-hy3-harness-eval-local-apply`",
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply_completion",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_upstream_evidence_interpretation_doc_records_claude_prompt_scan_contract():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")

    required_phrases = [
        "Source digest: `github-growth-20260618T181207.161132Z`",
        "https://github.com/omnigent-ai/omnigent/issues/701",
        "Claude-native second-message timeout",
        "configured tail\nlines",
        "non-empty status-footer line count",
        "whether a second message would time out",
        "pytest tests/test_harness_eval.py -q -k\nprovider_runtime_preflight",
        "prompt_scan_timeout_risk",
        "Raw terminal\npane text",
        "tokens, and credentials\nmust not be exported",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_ci_security_waiver_doc_records_label_only_rerun_contract():
    doc = (REPO_ROOT / "docs" / "ci-security-waiver.md").read_text(encoding="utf-8")

    required_phrases = [
        "Source digest: `github-growth-20260618T092043.842756Z`",
        "https://github.com/omnigent-ai/omnigent/pull/637",
        "does not change this repository's live CI",
        "label snapshot for the same workflow rerun attempt",
        "Scan conclusion `success` passes without a waiver.",
        "exact label-only waiver",
        "Comments, commit\n  messages, workflow inputs, environment variables, secrets, token values",
        "stale\n  label snapshot from an earlier attempt blocks the waiver path",
        "do not record credentials, private data,\n  or raw CI logs",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []
