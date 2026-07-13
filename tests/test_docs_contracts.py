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
    assert "classification-only matrix" in architecture
    assert "Claude-native prompt readiness" in architecture
    assert "prompt_scan_timeout_risk" in architecture
    assert "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight" in architecture
    assert "agent_harness_provider_registration" in architecture
    assert "required_provider_config_missing" in architecture
    assert "pytest tests/test_harness_eval.py -q -k agent_harness_provider_registration" in architecture
    assert "upstream_evidence_capability_step" in architecture
    assert "compare_pull_request_approach_with_local_agent_behavior_before_draft" in architecture
    assert "privacy_boundary_review_only" in architecture
    assert "agent_harness_eval_cluster" in architecture
    assert "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster" in architecture
    assert "agent_harness_eval_cluster_local_apply" in architecture
    assert (
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply"
        in architecture
    )
    assert "agent_harness_eval_cluster_local_apply_completion" in architecture
    assert (
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply_completion"
        in architecture
    )
    assert "prop-hy3-harness-eval-local-apply" in architecture
    assert "skill_route_discovery_capability_pipeline" in architecture
    assert "classifier" in architecture
    assert "route_profiles" in architecture
    assert "bounded_local_apply_lanes" in architecture
    assert "skill_route_discovery_local_comparison" in architecture
    assert "skill_route_discovery_reverse_flow_test_validation_lane" in architecture
    assert "skill_route_discovery_local_apply" in architecture
    assert "skill_route_discovery_rnskill_docs_validation_lane" in architecture
    assert "skill_route_discovery_config_gate_boundary" in architecture
    assert "skill_route_discovery_local_apply_completion" in architecture
    assert "skill_route_discovery_unlocked_local_test_lane_apply" in architecture
    assert "skill_route_discovery_focused_local_test_validation" in architecture
    assert "skill_route_discovery_focused_validation_activation_external_handoff" in architecture
    assert "skill_route_discovery_focused_validation_activation_external_acceptance" in architecture
    assert "skill_route_discovery_focused_validation_residual_adjacent_queue" in architecture
    assert "skill_route_discovery_residual_adjacent_harness_eval_local_apply" in architecture
    assert "skill_route_discovery_residual_adjacent_harness_eval_local_comparison" in architecture
    assert "skill_route_discovery_residual_adjacent_unlocked_local_lane_apply" in architecture
    assert "skill_route_discovery_residual_adjacent_focused_local_validation" in architecture
    assert (
        "skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff"
        in architecture
    )
    assert (
        "skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance"
        in architecture
    )
    assert "skill_route_discovery_adjacent_harness_eval_handoff" in architecture
    assert (
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        in architecture
    )
    assert (
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_unlocked_local_test_lane_apply"
        in architecture
    )
    assert (
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation"
        in architecture
    )
    assert (
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_local_validation"
        in architecture
    )
    assert (
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_validation_activation_external"
        in architecture
    )
    assert "record_skill_route_discovery_focused_local_test_validation_results" in architecture
    assert "close_skill_route_discovery_focused_local_test_validation_with_outcome" in architecture
    assert "record_skill_route_discovery_residual_adjacent_focused_local_validation_results" in architecture
    assert "close_skill_route_discovery_residual_adjacent_focused_local_validation_with_outcome" in architecture
    assert "build_skill_route_discovery_focused_validation_body_free_command_results" in architecture
    assert "prop-skill-reverse-flow-focused-test-validation" in architecture


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


def test_upstream_evidence_interpretation_doc_records_approval_ask_surfacing_watch():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    required_doc_phrases = [
        "## Approval ASK Surfacing Watch",
        "Source digest: `github-growth-20260619T035206.981359Z`",
        "https://github.com/omnigent-ai/omnigent/pull/764",
        "re-filed eight quarantined\napproval e2e tests",
        "INPUT-phase approval tests passed",
        "TOOL_CALL, TOOL_RESULT, OUTPUT, and sub-agent-tunneled ASK cases failed\nconsistently",
        "collapse-to-DENY behavior",
        "phase-specific approval\nsurfacing",
        "approval e2e and mock workflow fixtures",
        "manual/local mode handling",
        "test-branch and known-failure metadata",
        "distinguishes INPUT, TOOL_CALL,\nTOOL_RESULT, OUTPUT, and sub-agent ASK phases",
        "without exporting raw prompts,\ntool arguments, session identifiers, private chats, tokens, credentials",
        "Privacy-leakage scenarios remain review-only",
        "phase names, booleans, failure classes, counts, and\nhashes",
    ]
    required_architecture_phrases = [
        "Approval surfacing regressions should be tracked by phase",
        "Omnigent PR #764 watch item",
        "INPUT, TOOL_CALL, TOOL_RESULT, OUTPUT, and sub-agent ASK phases",
        "privacy-leakage cases kept review-only",
        "body-free metadata such as phase names, booleans, failure classes, counts, and hashes",
    ]

    missing_doc = [phrase for phrase in required_doc_phrases if phrase not in doc]
    missing_architecture = [
        phrase for phrase in required_architecture_phrases if phrase not in architecture
    ]

    assert missing_doc == []
    assert missing_architecture == []


def test_known_failure_metadata_preflight_contract_is_documented():
    doc = (REPO_ROOT / "docs" / "upstream-evidence-interpretation.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    required_doc_phrases = [
        "## Known-Failure Metadata Preflight",
        "Source digest: `github-growth-20260621T025207.809488Z`",
        "test/remove-known-failures branch",
        "`known_failure_metadata_preflight` compares expected and\ncurrent known-failure metadata",
        "`known_failure_metadata_stale`",
        "`test_gating_should_refresh`",
        "hashed removed/added failure IDs",
        "raw test names, raw failure text, quarantine bodies, and\nprivate paths remain omitted",
        "pytest tests/test_harness_eval.py -q -k known_failure_metadata_preflight",
    ]
    required_architecture_phrases = [
        "`known_failure_metadata_preflight` fixtures run before a growth pass treats test evidence as current",
        "detects absent metadata, empty current metadata, removed entries",
        "`test_gating_should_refresh` plus body-free recovery hints",
        "Failure IDs are represented only as hashes",
        "does not edit quarantine files or execute tests",
        "pytest tests/test_harness_eval.py -q -k known_failure_metadata_preflight",
    ]

    missing_doc = [phrase for phrase in required_doc_phrases if phrase not in doc]
    missing_architecture = [phrase for phrase in required_architecture_phrases if phrase not in architecture]

    assert missing_doc == []
    assert missing_architecture == []


def test_windows_runner_degraded_mode_contract_is_documented():
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    required_phrases = [
        "When Windows-native support explicitly allows degraded mode",
        "`provider_windows_runner_degraded_mode`",
        "`local_replay_only: true`",
        "provider runtime launch denied",
        "`provider_windows_runner_capability_unavailable`",
        "dependency names, capability names",
        "Windows dependency names, Windows capability names",
    ]

    missing_architecture = [phrase for phrase in required_phrases if phrase not in architecture]

    assert missing_architecture == []


def test_kubernetes_sandbox_provider_preflight_contract_is_documented():
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    required_phrases = [
        "Kubernetes managed-sandbox provider metadata",
        "`kubernetes_sandbox` block",
        "`provider_kubernetes_sandbox_config_missing`",
        "`provider_kubernetes_sandbox_config_malformed`",
        "`provider_kubernetes_sandbox_credential_env_inline`",
        "`provider_kubernetes_sandbox_launch_token_missing`",
        "`provider_kubernetes_sandbox_token_value_configured`",
        "`cluster_access_attempted: false`",
        "Kubernetes namespaces, Kubernetes images, Kubernetes service accounts",
        "Kubernetes token values",
    ]

    missing_architecture = [phrase for phrase in required_phrases if phrase not in architecture]

    assert missing_architecture == []


def test_skill_route_discovery_doc_records_capability_pipeline_pass1():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "## Skill Route Discovery Capability Pipeline",
        "Source digest: `github-growth-20260712T185308.158673Z`",
        "`skill_route_discovery_capability_pipeline`",
        "`classifier`",
        "`route_profiles`",
        "`bounded_local_apply_lanes`",
        "`codex_workflow_gate`",
        "`skill_route_discovery_first`",
        "`generic_skill_workflow`",
        "local comparison before any unlock",
        "`runtime_action=none`",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline",
        "### Pass 2 reverse-flow local test validation lane",
        "Source digest: `github-growth-20260712T191308.244484Z`",
        "`prop-skill-pipeline-reverse-flow-test`",
        "`skill_route_discovery_local_comparison`",
        "`reverse_flow_test_validation_lane`",
        "`prop-skill-pipeline-rnskill-docs`",
        "`prop-skill-pipeline-config-gates`",
        "### Pass 3 local apply handoff (rnskill docs + config gates)",
        "Source digest: `github-growth-20260712T193308.312710Z`",
        "`skill_route_discovery_local_apply`",
        "`skill_route_discovery_rnskill_docs_validation_lane`",
        "`skill_route_discovery_config_gate_boundary`",
        "replay_skill_route_discovery_local_apply_then_continue_to_pass4",
        "### Pass 4 reverse-flow local apply completion",
        "Source digest: `github-growth-20260712T195308.158137Z`",
        "`skill_route_discovery_local_apply_completion`",
        "apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external",
        "### Unlocked reverse-flow local test lane apply",
        "Source digest: `github-growth-20260712T203308.588539Z`",
        "`skill_route_discovery_unlocked_local_test_lane_apply`",
        "`prop-skill-reverse-flow-test-lane`",
        "run_focused_local_test_validation_then_keep_activation_external",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_unlocked_local_test_lane_apply",
        "### Focused local test validation (body-free result surface)",
        "Source digest: `github-growth-20260712T205308.160735Z`",
        "`skill_route_discovery_focused_local_test_validation`",
        "run_focused_local_test_validation_with_body_free_command_hashes",
        "record_focused_local_test_validation_pass_and_keep_activation_external",
        "keep_activation_external_after_focused_local_test_validation",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation",
        "### Focused local test validation result recording",
        "Source digest: `github-growth-20260712T211308.627162Z`",
        "`prop-skill-reverse-flow-focused-test-validation`",
        "record_skill_route_discovery_focused_local_test_validation_results",
        "normalize_skill_route_discovery_focused_validation_command_results",
        "### Focused validation activation-external handoff",
        "Source digest: `github-growth-20260712T213308.729900Z`",
        "`skill_route_discovery_focused_validation_activation_external_handoff`",
        "package_activation_external_handoff_after_focused_validation_pass",
        "blocked_until_focused_validation_recorded",
        "### Focused validation close-with-outcome + activation-external acceptance",
        "Source digest: `github-growth-20260712T215308.239488Z`",
        "`prop-skill-reverse-flow-focused-test-validation`",
        "build_skill_route_discovery_focused_validation_body_free_command_results",
        "close_skill_route_discovery_focused_local_test_validation_with_outcome",
        "`skill_route_discovery_focused_validation_activation_external_acceptance`",
        "accept_activation_external_package_after_focused_validation_pass",
        "blocked_until_activation_external_handoff_ready",
        "keep_activation_external_and_queue_residual_adjacent_harness_eval",
        "### Focused validation residual adjacent queue after acceptance",
        "Source digest: `github-growth-20260712T221308.618244Z`",
        "`prop-skill-reverse-flow-continue-local-validation`",
        "`skill_route_discovery_focused_validation_residual_adjacent_queue`",
        "queue_residual_adjacent_harness_eval_after_focused_validation_acceptance",
        "hand_off_residual_adjacent_rows_to_agent_harness_eval_cluster_local_apply",
        "blocked_until_activation_external_acceptance",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_validation_residual_adjacent",
        "### Residual adjacent harness-eval local apply after residual queue",
        "Source digest: `github-growth-20260712T223308.255959Z`",
        "`prop-residual-adjacent-fortress-harness-eval`",
        "`skill_route_discovery_residual_adjacent_harness_eval_local_apply`",
        "hand_off_selected_residual_adjacent_row_to_agent_harness_eval_cluster_local_apply",
        "run_agent_harness_eval_local_comparison_for_residual_adjacent_row",
        "blocked_until_residual_adjacent_queue_ready",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_harness_eval_local_apply",
        "### Residual adjacent harness-eval local comparison after residual local apply",
        "Source digest: `github-growth-20260712T225308.154547Z`",
        "`skill_route_discovery_residual_adjacent_harness_eval_local_comparison`",
        "unlock_documentation_test_or_code_patch_after_residual_adjacent_harness_local_comparison",
        "apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external",
        "blocked_until_residual_adjacent_harness_eval_local_apply_ready",
        "skill_route_unlocked_local_lanes",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_harness_eval_local_comparison",
        "### Residual adjacent unlocked local lane apply after harness comparison",
        "Source digest: `github-growth-20260712T231308.528323Z`",
        "`skill_route_discovery_residual_adjacent_unlocked_local_lane_apply`",
        "apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external",
        "run_focused_local_validation_for_residual_adjacent_unlocked_lane_and_keep_activation_external",
        "blocked_until_residual_adjacent_harness_local_comparison_ready",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_unlocked_local_lane_apply",
        "### Residual adjacent focused local validation after unlocked lane apply",
        "Source digest: `github-growth-20260712T233308.367716Z`",
        "`skill_route_discovery_residual_adjacent_focused_local_validation`",
        "run_residual_adjacent_focused_local_validation_with_body_free_command_hashes",
        "record_residual_adjacent_focused_local_validation_pass_and_keep_activation_external",
        "keep_activation_external_after_residual_adjacent_focused_local_validation",
        "record_skill_route_discovery_residual_adjacent_focused_local_validation_results",
        "close_skill_route_discovery_residual_adjacent_focused_local_validation_with_outcome",
        "blocked_until_residual_adjacent_unlocked_local_lane_apply_ready",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_local_validation",
        "### Residual adjacent focused validation activation-external handoff",
        "Source digest: `github-growth-20260713T010202.728081Z`",
        "`skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`",
        "package_activation_external_handoff_after_residual_adjacent_focused_validation_pass",
        "keep_activation_external_and_note_remaining_residual_adjacent_rows",
        "remaining_residual_adjacent_proposal_ids",
        "blocked_until_residual_adjacent_focused_validation_recorded",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_validation_activation_external",
        "### Residual adjacent focused validation activation-external acceptance",
        "Source digest: `github-growth-20260713T021123.550143Z`",
        "`skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`",
        "accept_activation_external_package_after_residual_adjacent_focused_validation_pass",
        "blocked_until_residual_adjacent_activation_external_handoff_ready",
        "### Adjacent fortress harness-eval handoff",
        "`skill_route_discovery_adjacent_harness_eval_handoff`",
        "`prop-harness-fortress-local-eval`",
        "run_agent_harness_eval_local_comparison_for_selected_general_agent_row",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_adjacent_fortress_handoff",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in doc]
    assert missing == []


def test_skill_route_discovery_doc_records_bounded_matrix():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260618T062043.878926Z`",
        "`github-growth-20260703T171922.860113Z`",
        "`p2-agent-harness-eval-routing`",
        "`github-growth-20260618T215207.204133Z`",
        "`github-growth-20260618T233207.218276Z`",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "https://github.com/pretinhuu1-boop/threejs-game-skills",
        "`github-growth-20260624T055355.537474Z`",
        "`skill_route_discovery` is a bounded local capability\nroute, not a skill activation route",
        "may map only to documentation, config,\ntest, or code_patch work",
        "each selected lane must carry local validation before\nactivation",
        "FableCodex-style workflow evidence can select the\n`codex_workflow_gate` profile",
        "COMPASS-style state or collaboration evidence can\nselect `skill_ecosystem_state_handoff`",
        "source-cited domain skill evidence can\nselect `source_cited_domain_research`",
        "Three.js or Phaser skill bundles can\nselect `game_frontend_workflow`",
        "Source digest `github-growth-20260628T120729.553038Z`",
        "`skill_route_discovery_current_pass_completion_lane`",
        "`p1-skill-route-discovery-general`",
        "`p2-game-frontend-skill-profile`",
        "`p3-skill-ecosystem-state-handoff`",
        "non-network game frontend workflow acceptance criteria",
        "top-level replay bundle groups those commands\nby proposal ID",
        "Runtime action, upstream skill\nactivation, upstream agent activation",
        "Proposal evidence refs must cite selected digest `item_id` values,\nnot raw repository URLs",
        "truncated item IDs, or\nnon-selected evidence",
        "candidates must not supply or expand them",
        "No upstream code, install scripts, prompts, or skill bodies were adopted.",
        "FableCodex describes Codex workflow gates, COMPASS Skills\n"
        "describes local skills for clarification, task memory, and collaboration\n"
        "profiles, and Three.js Game Skills describes a domain director with specialist\n"
        "skills and verification helpers",
        "does not\n"
        "grant permission to install, execute, scaffold, profile, generate assets, or\n"
        "activate any upstream skill package",
        "clarified by\n`github-growth-20260618T193207.157147Z`",
        "`baskduf/FableCodex`",
        "`dongshuyan/compass-skills`",
        "`majidmanzarpour/threejs-game-skills`",
        "documentation",
        "config",
        "test",
        "code_patch",
        "Blocked discovery actions include install, enable, run, execute,",
        "creation does not install a skill",
        "deletion does not delete a local\nskill",
        "repository-level and README-level",
        "not enough to promote a candidate\nto executable skill routing",
        "## Acceptance Criteria",
        "cite only frozen digest evidence or derived item evidence already\n  present in the run package",
        "do not trust README claims as implementation\n  parity",
        "map the discovery route only to documentation, config, test, or\n  code_patch work",
        "repository popularity or external examples do not replace local tests",
        "record a rollback ref or artifact before self-modification",
        "do not automatically import, install, enable, execute, clone,\n  scaffold, or otherwise trust external skill code",
        "do not expose, print, upload, publish, or share tokens,\n  credentials, secrets, private keys, private chats, PII, or personal data",
        "Fork or mirror evidence is lineage evidence, not independent activation\npressure",
        "`upstream_source_url`,\n`forked_from_url`, or `parent_source_url`",
        "records the related\npublic source URLs for audit",
        "does not increase\n`candidate_count`, proposal lane count, activation lane candidate count",
        "Repeated public activity around the same skill repository name can now affect\nonly local discovery selection and metadata",
        "Repository trend, fork, and push\nitems that classify as `skill_workflow`",
        "`route_activity_pressure` summary with hashed project keys",
        "does not create install,\nenable, clone, run, execute, deletion, provider launch, remote execution, or\nexternal skill activation authority",
        "`activation_manifest` as a compact replay surface for bounded local work",
        "`activation_sequence`, an ordered\nsupervisor replay checklist",
        "source-lineage inspection, bounded local lane checks, local artifact\nproof",
        "`candidate_lane_intake` before the\nexpanded lane matrix",
        "operator-facing candidate selection surface",
        "downgraded lane pressure such as `install`, `execute`, or\n`runtime_execution`",
        "`external_skill_code_allowed: false`",
        "`term_route_review`, a compact body-free panel",
        "`agent`, `agents`, `codex`, `skill`, `skills`, and\n`workflow`",
        "repository popularity or term matches\ncan explain why evidence entered skill-route discovery",
        "do not add\nlanes, cite new evidence URLs",
        "`mixed_local_lane_probe`",
        "Codex, skill or skills, and workflow terms",
        "`agent_harness_eval_after_local_corroboration` as blocked until local\ncorroboration exists",
        "mixed Codex, skill, and workflow terms",
        "An explicit agent\nterm is recorded as `full_mixed_signal`, but it is no longer required",
        "before any broader harness evaluation",
        "The sequence is a replay\nsurface only",
        "does not install, clone, execute, scaffold, generate assets, or\nactivate upstream skill code",
        "`evidence_ref_mode` is `selected_item_ids_only`",
        "public repository URLs remain\nsource evidence in the frozen package, not manifest citations",
        "raw evidence URLs, raw\nsource URLs, raw target paths, and raw upstream bodies",
        "`preactivation_lane_selection`, a compact selector",
        "chooses one bounded local lane per ready route profile",
        "never selects\nwithout local artifact proof",
        "`profile_validation_replay`, a per-profile local\nchecklist",
        "`replay_local_test_lane_for_workflow_or_game_route`",
        "`review_local_config_lane_for_state_handoff`",
        "does\nnot add lanes, install skills, run upstream code",
        "`capability_window_completion`",
        "hashed anchoring proposals",
        "A ready completion panel means the four-pass\nslice has an operator-visible local result",
        "`local_lane_closure`, a per-lane\nclosure summary",
        "documentation, config, test, and code_patch readiness",
        "local\nartifact proof readiness, operator lane readiness, and activation blocker\nhashes",
        "`activation_handoff`, a final supervisor replay\ncontract",
        "external supervisor may\nreplay the already validated documentation, config, test, or code_patch lanes",
        "The kernel does not restart itself, launch providers,\nperform remote execution, activate upstream skills",
        "external harness execution, provider launch, remote\nexecution",
        "`activation_sequence_status`",
        "`completion_recovery`, a body-free repair\nselector",
        "repair missing required route profiles, repair local artifact proof,\nreplay provider-runtime preflight",
        "records only bounded lane names, missing\nroute profile names, blocker hashes, hint codes, and replay commands",
        "does\nnot export raw evidence URLs, raw source URLs, raw target paths, or upstream\nbodies",
        "`profile_validation_gate`, a final\nprofile-specific check",
        "FableCodex-style\n`codex_workflow_gate` rows must still prove\n`skill_route_discovery_first`",
        "`game_frontend_workflow` rows must be tied to the local test/frontend\nvalidation lane",
        "`skill_ecosystem_state_handoff` rows must be tied to\n"
        "the local config/state-boundary lane",
        "`next_pass_handoff`",
        "pass-to-pass\ncontinuity",
        "`pass2_handoff_packet`",
        "selected current-pass lane, queued bounded lanes, selected item IDs, candidate\nsource hashes, and mixed-route probe decision",
        "`mixed_skill_workflow_primary_route: skill_route_discovery`",
        "`agent_harness_eval_after_local_corroboration` remains blocked",
        "not a secondary-harness activation token",
        "`bounded_activation_preview`",
        "pass-2 replay\nsurface for the selected current-pass lane and queued bounded lanes",
        "It does not add lanes, cite raw repository URLs, activate the\nsecondary harness",
        "`local_lane_matrix`, a compact pre-activation\nsummary",
        "whether a FableCodex-style\n`codex_workflow_gate` has confirmed `skill_route_discovery_first`",
        "It does not add lanes, export raw source URLs or\nupstream bodies",
        "`pass3_handoff_packet`",
        "active final-pass lane and any queued bounded lane",
        "`agent_harness_eval_after_local_corroboration` remains blocked",
        "`pass3_active_window_review_packet`",
        "`p1-skill-route-discovery-matrix`",
        "`p2-skill-route-documentation`",
        "`skill_route_discovery_first`",
        "Qwen-AgentWorld-style general-agent evidence remains adjacent\n"
        "`agent_harness_eval_required`",
        "`pass1_handoff_packet`",
        "selected current-pass bounded lane",
        "`adjacent_general_agent_project_eval`",
        "`agent_harness_eval_required: true`",
        "`skill_route_discovery_inherited: false`",
        "does not add skill-route lanes, grant\nruntime action",
        "`recommended_local_lane_order` derived only from already bounded local lanes",
        "`skill_route_local_lane_candidates`",
        "derived directly from selected skill/workflow\nitems",
        "FableCodex, COMPASS Skills, and Three.js Game Skills-style rows expose\nonly documentation, config, test, and code_patch",
        "Mixed\nFableCodex-style rows keep the secondary harness lane blocked until local\ncorroboration",
        "general agent projects such as Omnigent do not appear in\nthis panel",
        "`skill_route_boundary_report`, a compact\noperator summary of that split",
        "`primary_route:\nskill_route_discovery`",
        "General agent-project rows such as Omnigent or xuefeng-agent keep\n`primary_route: agent_harness_eval_required`",
        "Mixed skill/workflow rows keep\n`agent_harness_eval_after_local_corroboration` blocked until local\ncorroboration exists",
        "it does not add lanes, expose raw source URLs, export upstream bodies, run an\nexternal harness",
        "`route_activation_preflight`, a supervisor\ngate",
        "FableCodex, COMPASS Skills, and Three.js Game Skills-style evidence can\nbe ready only for documentation, config, test, or code_patch validation",
        "Omnigent-style general agent-project evidence remains\n`agent_harness_eval_required`",
        "A ready preflight does not\ninstall, enable, run, clone, scaffold",
        "`continue_bounded_lane_validation_next_pass`",
        "`continue_skill_route_discovery_window`",
        "`repair_current_pass_before_continuing`",
        "`lane_validation_targets`",
        "operator-visible workload for the next pass",
        "COMPASS-style state-handoff route can therefore remain a local\nconfig validation target",
        "FableCodex-style workflow gates and Three.js game\nskill routes share a local test validation target",
        "The selected step now carries `promotion_proof`",
        "changed-file review, focused local validation, rollback artifact, and review\nnote evidence",
        "without exporting\nraw target paths",
        "`current_action`, a compact\nsupervisor row for the current scheduled pass",
        "show \"continue with the local test lane next pass\" directly at the top level",
        "`current_action_provider_runtime_preflight`",
        "`provider_runtime_preflight_sample_missing`",
        "raw\npreflight inputs, raw diagnostics, raw provider values",
        "`provider_runtime_promotion_checkpoint`",
        "provider-runtime sample gate, current-action preflight, and replay sample into a\nsingle body-free supervisor row",
        "selected bounded\nlocal lane may continue after local provider-runtime replay",
        "not provider\nlaunch authority",
        "not four-pass slice completion",
        "`profile_validation_checklist`, a compact mirror",
        "`selected_current_pass_profile` or `queued_profile_for_later_pass`",
        "FableCodex-style\n`codex_workflow_gate` and Three.js-style `game_frontend_workflow` profiles can\nbe selected for the local test lane",
        "COMPASS-style\n`skill_ecosystem_state_handoff` remains queued for the local config lane",
        "repeats the per-profile replay checklist through\n`profile_validation_replay`",
        "`summary_signal_audit` before activation",
        "accepted, ignored, or collapsed as duplicates",
        "matched route terms, route\nprofiles, bounded proposal kinds, and hashed evidence URLs",
        "generic agent-runtime summary remains ignored by this route",
        "`route_validation_contract` on every candidate\ninventory row and proposal-lane row",
        "`skill_route_discovery_first_before_workflow_gate`",
        "`local_frontend_validation_before_game_skill_activation`",
        "`state_handoff_boundary_before_profile_or_memory_write`",
        "denied provider launch, denied remote execution, and denied\nraw upstream body export before activation",
        "`profile_lane_acceptance_contract`",
        "FableCodex-style\n`codex_workflow_gate` evidence must preserve `skill_route_discovery_first`",
        "Three.js `game_frontend_workflow` evidence starts in\n"
        "the local test/frontend validation lane",
        "COMPASS-style\n`skill_ecosystem_state_handoff` evidence starts in the local config/state\nboundary lane",
        "The pass-2 handoff packet embeds the same contract",
        "`pass1_validation_queue`",
        "`profile_validation_lanes`",
        "COMPASS-style state handoff exposes the local config\nor boundary-review lane",
        "FableCodex-style workflow evidence exposes the\nlocal test lane with `first_route_required` and `first_route_confirmed`",
        "`p2-threejs-game-skill-docs`",
        "`p3-codex-workflow-gate-config`",
        "Adjacent general-agent anchors such as\n`p4-general-agent-harness-eval`",
        "`trend:omnigent-ai/omnigent`",
        "`agent_harness_eval_required` rows with\n`skill_route_discovery_inherited: false`",
        "The queue is a replay surface, not an activation token",
        "## Evidence Citation And Uncertainty",
        "cite only selected `item_id` values\nin `evidence_refs`",
        "must not cite repository URLs, owner/repository names,\ntruncated item IDs",
        "review layer derives accepted evidence URLs from those frozen `item_id` values",
        "accepted candidates use only documentation, config, test, or code_patch lanes",
        "every accepted `evidence_ref` is a selected `item_id` from the frozen\n"
        "evidence package",
        "URL strings such as `https://github.com/baskduf/FableCodex`\n"
        "are valid source evidence in the package, but they are not valid proposal\n"
        "citations",
        "generic, README-level, sparse",
        "`missing_detail_risk`",
        "proposal uncertainty must mention that missing detail\nrisk",
        "body-free `evidence_strength` summary",
        "Generic pull request or push clusters are\n`weak_generic_upstream_movement`",
        "separate\nbody-free `local_corroboration` record",
        "A route hint, CI word, test word, or\ngeneric PR title inside the upstream evidence does not count as corroboration",
        "not activation-ready merely because its candidate lanes\nare otherwise bounded",
        "weak generic upstream movement is\n`review_weak_evidence_before_activation`",
        "generic upstream movement with local\ncorroboration can become `ready_for_local_proposal_activation`",
        "The harness also renders a `discovery_checklist` for operator review before\nlocal activation",
        "hashed source, capability,\nallowed local lane, required tests, rollback note, runtime action, and external\nactivation flag",
        "source URLs are represented\nas hashes",
        "required tests include\n`pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`",
        "`completion_consistency_guard`",
        "selected local lane set must match across those surfaces",
        "Diagnostics are reported only as hashes",
        "`final_lane_policy_inventory`",
        "allowed local lane set, proposal kinds, selected local lanes",
        "replay-command hashes",
        "derived from `final_route_handoff_manifest`,\n"
        "`route_validation_lane_queue`, and `secondary_harness_bridge`",
        "does not add\nlanes, accept raw repository URLs, export upstream bodies",
        "`pass4_completion_handoff`",
        "derived from `pass4_local_lane_validation`",
        "required rollback ref and artifact contract",
        "per-profile\ninspection requirements",
        "recovery hint codes",
        "`external_supervisor_replay_without_kernel_restart`",
        "`pass4_operator_replay_manifest`",
        "compare changed files with hashed lane artifact\ntargets",
        "raw target paths, raw replay commands, raw source URLs",
        "`agent_harness_eval_required` with `skill_route_discovery_inherited: false`",
        "raw source URLs, raw evidence URLs, raw target paths, and upstream bodies\n"
        "are not exported",
        "rollback\nnotes require a rollback ref and artifact before source changes",
        "runtime action\nremains `none`, and external skill activation remains false",
        "Each checklist row and activation row also carries\n`inspection_requirements`",
        "selected digest item IDs or frozen\ndigest evidence",
        "body-free repository summaries, source-lineage metadata, local\nartifact targets",
        "installing upstream skills, running upstream skill code, clone-and-run behavior",
        "preactivation trust boundary rejects activation rows that omit or\nweaken this inspection contract",
        "`implementation_intake_preflight` before supervisor\npromotion",
        "reports `ready` only when the preactivation trust boundary\npassed",
        "exports target paths only as hashes",
        "keeps runtime action, external\nskill activation, external skill code, and raw upstream bodies denied",
        "not yet a local implementation lane",
        "The final local handoff view is `operator_handoff`",
        "exports only target path hashes and source counts",
        "carries recovery hint codes for blocked or degraded lanes",
        "`provider_runtime_control`",
        "For a provider-runtime-control window that is still in pass 1",
        "The `provider_runtime_sample_gate` may be `ready`, while\n`capability_window_completion` remains `blocked`",
        "prevents a harmless local\nprovider preflight sample from being mistaken for permission to launch a\nprovider",
        "`provider_runtime_interpretation_panel`",
        "diagnostics and\nrecovery hints only, followed by local provider-runtime replay",
        "next safe action",
        "hashed hint codes",
        "denies runtime action, external skill activation,\nexternal harness execution, provider launch, remote execution",
        "## Focused Pass 3 Profile Proof Checklist",
        "Source digest `github-growth-20260628T050729.790102Z`",
        "`profile_validation_requirements`",
        "local route-profile contracts, not from upstream skill bodies",
        "`game_frontend_workflow` must prove local frontend or test validation covers a\n"
        "  runnable game workflow and asset/provider boundaries",
        "`skill_ecosystem_state_handoff` must prove state handoff metadata remains\n"
        "  local config without profile or memory writes",
        "General-agent projects without\nskill workflow signals remain adjacent `agent_harness_eval_required`",
        "\"evidence_refs\": [\"fablecodex-codex-skill-workflow\"]",
        "\"evidence_refs\": [\"https://github.com/baskduf/FableCodex\"]",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260709T005850_pass2_checkpoint():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260709T005850.776521Z`",
        "`current_pass2_skill_benchmark_checkpoint`",
        "`reverse-flow-skill` remains a Codex workflow-gate skill route",
        "`rnskill` remains a generic SKILL.md-compatible collection",
        "`Cognitive-Core-Skills` remains a skill repository\nfirst",
        "blocked secondary hint toward\nagent-harness evaluation",
        "after skill-route\nvalidation only through documentation, test, or code_patch lanes",
        "Runtime action, external skill\nactivation, external harness execution",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260709T005850`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_route_discovery_catalog():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "## Route Discovery Catalog",
        "The reusable lesson is a category map, not a source import",
        "Workflow-gate package",
        "Evidence gates, review ledgers, inspection habits, verification routines",
        "Show the local gate in docs or a focused regression before changing runtime behavior",
        "Installing the upstream workflow or treating its README as proof",
        "State and alignment skill system",
        "Task memory, collaboration profile, clarification gate, repo-local task graph",
        "storage, retention, correction, and privacy boundaries",
        "Creating profile or memory behavior from repository presence alone",
        "Domain director or specialist bundle",
        "Director skill, specialist skills, scaffold, packaged helpers",
        "bundled scaffolds and helpers as evidence to inspect",
        "Running installer, scaffold, browser checker, asset generator, credential probe",
        "documentation, config, test, or code_patch",
        "recorded as rejected or downgraded evidence, never as an activation request",
        "body-free `route_profile_catalog`",
        "`codex_workflow_gate`",
        "`skill_ecosystem_state_handoff`",
        "`game_frontend_workflow`",
        "`source_cited_domain_research`",
        "`generic_skill_workflow`",
        "These profiles are triage metadata only",
        "do not create install, scaffold, asset-generation, browser-run,\n"
        "profile-writing, upstream dataset import, advice generation, provider-launch,\n"
        "remote-execution, or external skill activation",
        "`bounded_route_profile_matrix`",
        "maps observed `generic_skill_workflow`,\n"
        "`game_frontend_workflow`, and `skill_ecosystem_state_handoff` evidence",
        "selected local lane, validation target, replay command, candidate source hashes",
        "raw target path export, and upstream body export remain denied",
        "`current_pass_validation_cases`",
        "`p1_skill_route_discovery_generic_views`",
        "`p2_skill_route_discovery_game_frontend`",
        "`p3_skill_ecosystem_state_handoff_config`",
        "Generic\nPython agent-skill workflow evidence may satisfy the first case through\n`generic_skill_workflow`",
        "Game frontend\nsignals may choose only a documentation/config/test/code_patch lane after\n`skill_route_discovery`",
        "`pass3_route_discovery_index`",
        "`pass3_preflight_queue`",
        "`pass3_current_wake_acceptance_packet`",
        "`p1_skill_route_discovery_index`",
        "`p2_skill_workflow_docs`",
        "`p3_skill_route_metadata_config`",
        "`p1-skill-route-discovery-index`, `p2-skill-route-discovery-docs`, and\n"
        "`p3-agent-harness-eval-fixtures`",
        "joins the\n`pass3_route_discovery_index` and `pass3_activation_handoff` surfaces",
        "`source_cited_domain_research`, `game_frontend_workflow`, and\n"
        "`skill_ecosystem_state_handoff` profiles are present",
        "Qwen-AgentWorld-style general-agent evidence remains\n"
        "`agent_harness_eval_required` with `skill_route_discovery_inherited: false`",
        "only documentation, config, test, or\ncode_patch as allowed local lanes",
        "profile writes, memory writes, external\nharness execution, provider launch, remote execution",
        "`active_pass1_proposal_replay_lane`",
        "`active_pass1_activation_gate`",
        "`p1-skill-route-discovery-docs-and-probe`",
        "`p2-skill-route-discovery-test-fixtures`",
        "`p3-game-frontend-skill-profile-discovery`",
        "`external_supervisor_after_validation`",
        "runnable examples,\nvisual assets, frontend testability",
        "`current_pass3_route_readiness_index`",
        "distinguishes skill-route rows that are ready for bounded\nlocal validation",
        "Qwen-AgentWorld-style general-agent project evidence stays adjacent",
        "does not inherit `skill_route_discovery`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T232200_pass3_skill_workflow_probe():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T232200.034561Z`",
        "`skill_route_discovery_current_pass3_proposal_lane`",
        "`lingbol088-spec/reverse-flow-skill`",
        "`Pluviobyte/rnskill`",
        "`NVIDIA-BioNeMo/bionemo-agent-toolkit`",
        "`p1_skill_route_discovery_probe` keeps the Codex reverse-flow repository in\n"
        "the bounded local test lane",
        "`p2_codex_skill_workflow_profile` checks the\n"
        "`codex_workflow_gate` profile through the bounded config lane",
        "`p3_generic_skill_workflow_docs` keeps generic `SKILL.md` collection evidence\n"
        "in the documentation lane",
        "`p4_bionemo_domain_skill_toolkit_guard` keeps the\n"
        "domain-specific BioNeMo skill-toolkit signal in the test lane",
        "documentation, config, test, and code_patch as the only allowed\nlocal lanes",
        "runtime adoption,\nexternal skill activation, provider launch, external harness execution, remote\n"
        "execution",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T232200`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T000200_pass1_hy3_preflight_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T000200.125943Z`",
        "`skill_route_discovery_current_pass1_focused_review_lane`",
        "`Pluviobyte/rnskill` is kept as\ngeneric `SKILL.md` collection evidence",
        "`lingbol088-spec/reverse-flow-skill` is kept as Codex workflow-gate evidence",
        "`skills/reverse-flow`,\n`SKILL.md`, local sandbox and CTF framing",
        "`shepherd-agents/shepherd` remains adjacent\n`agent_harness_eval_required` evidence",
        "inherits no `skill_route_discovery` lane",
        "`skill_route_discovery_hy3_provider_mcp_preflight_lane`",
        "`p4-hy3-provider-mcp-preflight`",
        "Hy3 API and MCP issues are provider/tooling\nintegration pressure, not activation authority",
        "documentation, config, or test follow-up",
        "configuration detection, endpoint\nshape validation, required environment-key presence, MCP stdio metadata",
        "Provider runtime launch, external harness\nexecution, network calls, remote execution",
        "raw\nprovider config export, API-key hardcoding, and raw secret value export remain\ndenied",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260708T000200`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T004159_pass3_operator_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T004159.978474Z`",
        "`skill_route_discovery_current_digest_20260708T004159_pass3_operator_handoff`",
        "derived from the pass-2 scope recompute gate",
        "`lingbol088-spec/reverse-flow-skill` in the\nlocal test lane",
        "`Pluviobyte/rnskill`\nin the documentation lane",
        "code_patch follow-up still requires the controller-recomputed local\nvalidation scope",
        "`shepherd-agents/shepherd` remains an adjacent\n`agent_harness_eval_required` row",
        "no direct local lanes before harness\nevaluation",
        "`refs/blackhole/rollback/20260708T004349Z-skill-route-discovery-pass3-current-window`",
        "`docs/self-model.md` stayed unchanged",
        "Hy3\nprovider/MCP pressure as disabled follow-up only",
        "exports no raw source\nURLs, replay commands, upstream bodies, provider launches",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260708T004159`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T052834_pass1_focused_review_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T052834.687686Z`",
        "`skill_route_discovery_current_pass1_focused_review_lane`",
        "`p1-skill-route-discovery-reverse-flow`",
        "`p2-generic-skill-workflow-discovery`",
        "`p3-agent-harness-eval-fixture`",
        "`p4-route-policy-doc-note`",
        "`p5-route-metadata-consistency-check`",
        "`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate row",
        "`Pluviobyte/rnskill` remains the generic skill\nworkflow row",
        "install,\nrun, script execution, provider runtime, external harness execution, and remote\n"
        "execution are diagnostic pressure only",
        "`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and\n"
        "`shepherd-agents/shepherd` remain `agent_harness_eval_required` rows",
        "do not inherit `skill_route_discovery`",
        "only produce documentation, test, or code_patch follow-up after that gate",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T052834`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T110834_proposal_replay_rule():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "Proposal interpretation for `skill_route_discovery` must accept only\n"
        "documentation, config, test, or code_patch work",
        "Accepted proposals cite only\nselected digest `item_id` values in `evidence_refs`",
        "repository URLs, truncated\nitems, and newly discovered external evidence are rejected",
        "`github-growth-20260707T110834.493888Z`",
        "`p1_reverse_flow_skill_route_discovery`",
        "`p2_rnskill_generic_skill_route_discovery`",
        "`p3_skill_route_discovery_docs`",
        "`trend:lingbol088-spec/reverse-flow-skill-1`",
        "`trend:Pluviobyte/rnskill-1`",
        "rejects\n`https://github.com/Pluviobyte/rnskill` as a proposal citation",
        "runtime action, upstream skill activation, external harness execution, provider\n"
        "launch, and remote execution disabled",
        "`python -m pytest tests/test_proposal_eval.py -q -k current_skill_route_discovery`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T154109_pass4_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T154109.440320Z`",
        "`skill_route_discovery_current_digest_20260707T154109_pass4_completion_handoff`",
        "`p1-skill-route-discovery-codex-workflow` maps\n"
        "`lingbol088-spec/reverse-flow-skill` to the bounded local test lane",
        "`p2-generic-skill-workflow-discovery` keeps `Pluviobyte/rnskill` in the\n"
        "documentation lane",
        "documentation, config, test, or\ncode_patch outputs before activation",
        "`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and\n"
        "`shepherd-agents/shepherd` remain `agent_harness_eval_required` rows",
        "They do not inherit `skill_route_discovery`",
        "no direct local lanes before bounded harness evaluation",
        "records the rollback ref and artifact for the current\nkernel run",
        "exports validation commands only as hashes",
        "activation,\nrestart, promotion, provider launch, external harness execution, remote\n"
        "execution, memory writes, and runtime action disabled",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T154109`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T164109_pass3_validation_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T164109.440819Z`",
        "`skill_route_discovery_current_digest_20260707T164109_pass3_validation_lane`",
        "`skill_route_discovery_current_digest_20260707T164109_pass3_activation_review_packet`",
        "`lingbol088-spec/reverse-flow-skill` maps to the bounded local test lane",
        "`Pluviobyte/rnskill` maps to the bounded\ndocumentation lane",
        "documentation, config, test, and code_patch as local outputs",
        "ignored and recomputed by controller code as `local_validation_candidate`",
        "`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and\n"
        "`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows",
        "They inherit no skill-route lane",
        "no direct pre-eval implementation\nlane",
        "denying raw\nsource URLs, raw evidence URLs, replay commands, upstream bodies",
        "provider launch, memory\nwrites, remote execution, and runtime action",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T164109`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T170109_pass4_policy_completion():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T170109.447884Z`",
        "`skill_route_discovery_current_digest_20260707T170109_pass4_completion_handoff`",
        "`p1-skill-route-discovery-fixture`",
        "`p2-agent-harness-eval-shepherd`",
        "`p4-route-hint-policy-regression`",
        "`hdz717/reverse-flow-skill` and `lingbol088-spec/reverse-flow-skill` map to\n"
        "bounded local test rows",
        "`Pluviobyte/rnskill`\nmaps to the bounded documentation row",
        "documentation, config, test, or code_patch lanes",
        "`InternScience/Agents-A1`, `shepherd-agents/shepherd`, and\n"
        "`shepherd-agents/shepherd` PR #33 remain `agent_harness_eval_required` rows",
        "no direct local lanes before bounded harness evaluation",
        "`skill_route_discovery` maps only\nto documentation, config, test, or code_patch",
        "`agent_harness_eval` maps\nonly to documentation, test, or code_patch",
        "Route hints are not permission\ngrants",
        "runtime action, external skill activation, external\n"
        "harness execution, provider launch, remote execution, promotion, or restart",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T170109`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T194110_pass4_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T194110.112744Z`",
        "`skill_route_discovery_current_digest_20260707T194110_pass4_completion_handoff`",
        "`lingbol088-spec/reverse-flow-skill` to the bounded local test\nlane",
        "`Pluviobyte/rnskill` to the\nbounded documentation lane",
        "documentation, config, test, and code_patch as the only local outputs",
        "`shepherd-agents/shepherd` remains under\n`p3-agent-harness-eval-shepherd`",
        "`InternScience/Agents-A1` and\n`TianhangZhuzth/Fundamental-Ava` remain under\n"
        "`p4-agent-harness-eval-comparative-agent-projects`",
        "They inherit no\n`skill_route_discovery` lane",
        "no direct documentation, test, or\ncode_patch lane before bounded local agent-harness evaluation",
        "`docs/self-model.md` stayed unchanged",
        "exports no raw source URLs,\nreplay commands, target paths, upstream bodies",
        "promotion, restart, remote execution, or activation authority",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T194110`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T212110_pass1_domain_guard():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260707T212110.239635Z`",
        "`skill_route_discovery_current_pass1_focused_review_lane`",
        "`lingbol088-spec/reverse-flow-skill` to the bounded local test lane",
        "`Pluviobyte/rnskill` to the documentation lane",
        "`NVIDIA-BioNeMo/bionemo-agent-toolkit` stays in the same skill-route discovery\nsurface",
        "documentation, config, test, or code_patch candidates",
        "citation, data, advice, and provider boundary",
        "Install,\nruntime execution, provider launch, upstream dataset import, and external skill\nactivation remain denied",
        "`InternScience/Agents-A1` and\n`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows",
        "inherit no skill-route lane before local harness evaluation",
        "`refs/blackhole/rollback/20260707T212110Z-skill-route-discovery-pass1`",
        "`docs/self-model.md` unchanged",
        "exports no raw source URLs, replay\ncommands, upstream bodies, provider launches, remote execution, promotion,\nrestart, or activation authority",
        "`python -m pytest tests/test_skill_routing.py -q -k 20260707T212110`",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_current_pass3_validation_route_packet():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "github-growth-20260706T221555.480207Z",
        "`current_pass3_validation_route_packet`",
        "`lingbol088-spec/reverse-flow-skill` is the only skill-route row",
        "bounded local validation candidate in the test lane",
        "`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,\n"
        "`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`",
        "no selected skill package, no `SKILL.md`\nevidence, or no explicit skill workflow route signal",
        "`agent_harness_eval_required`",
        "inherit no `skill_route_discovery` route",
        "no direct implementation lanes before local harness evaluation",
        "each row's `evidence_refs` contains only its\nselected digest `item_id`",
        "never repository URLs or added external evidence",
        "Replay commands are exported only as hashes",
        "runtime action, upstream skill\nactivation, upstream agent activation, external harness execution",
        "python -m pytest tests/test_proposal_eval.py -q -k current_pass3_validation_route_packet",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_current_pass4_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "github-growth-20260707T050834.384415Z",
        "`skill_route_discovery_current_pass4_completion_handoff`",
        "rollback ref, a rollback artifact path",
        "validation command hashes",
        "`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate row",
        "`Pluviobyte/rnskill` remains the generic skill workflow row",
        "Install, run, script execution, provider runtime,\nexternal harness execution, and remote execution pressure stays diagnostic",
        "`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and\n"
        "`shepherd-agents/shepherd`",
        "do\nnot inherit `skill_route_discovery`",
        "no direct implementation lane before\nlocal harness evaluation",
        "python -m pytest tests/test_skill_routing.py -q -k 20260707T050834",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T185850_pass4_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T185850.414401Z`",
        "`skill_route_discovery_current_digest_20260708T185850_pass4_completion_handoff`",
        "`lingbol088-spec/reverse-flow-skill` maps to the\nlocal test lane",
        "`Pluviobyte/rnskill`\nmaps to the documentation lane",
        "`shepherd-agents/shepherd`, `Tencent-Hunyuan/Hy3`, and the Blender/Seedance\nworkflow-usecase repository",
        "`agent_harness_eval_required`",
        "inherit no `skill_route_discovery` lane",
        "nested local-kernel replay remains\nblocked by the review-only automation/bug checklist",
        "PYTHONPATH=src python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k 20260708T185850",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T203850_pass1_validation_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T203850.668356Z`",
        "`skill_route_discovery_current_digest_20260708T203850_pass1_validation_lane`",
        "`lingbol088-spec/reverse-flow-skill`\nmaps to `p1-skill-route-discovery-reverse-flow`",
        "`Pluviobyte/rnskill` maps to\n`p2-skill-route-discovery-rnskill`",
        "`shepherd-agents/shepherd` and `Tencent-Hunyuan/Hy3` remain adjacent\n"
        "`p3-agent-harness-eval-shepherd` and `p4-agent-harness-eval-hy3` rows",
        "`p5-agent-workflow-usecase-eval` anchor stays queued without a selected item",
        "expected triggers, bounded local lanes, minimal\nacceptance checks",
        "raw source URLs, evidence URLs, replay commands, target paths,\nupstream bodies",
        "python -m pytest tests/test_skill_routing.py -q -k 20260708T203850",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T205851_pass2_validation_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T205851.045193Z`",
        "`skill_route_discovery_current_digest_20260708T205851_pass2_validation_lane`",
        "`lingbol088-spec/reverse-flow-skill`\nmaps to `p1-skill-route-discovery-reverse-flow`",
        "`Pluviobyte/rnskill` maps to `p2-generic-skill-route-discovery`",
        "may lead only to documentation, config, test, or code_patch work after local\nvalidation",
        "`shepherd-agents/shepherd` and `Tencent-Hunyuan/Hy3` remain adjacent\n"
        "`p3-agent-harness-eval-shepherd` and `p4-agent-harness-eval-hy3` rows",
        "`p5-agent-workflow-usecase-eval` anchor remains queued without a selected\n"
        "workflow-usecase item",
        "raw source\nURLs, evidence URLs, replay commands, target paths, upstream bodies, install",
        "profile writes, memory writes, promotion, and restart remain disabled",
        "python -m pytest tests/test_skill_routing.py -q -k 20260708T205851",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T182110_operator_review_dossier():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "github-growth-20260707T182110.051391Z",
        "`skill_route_discovery_active_pass4_operator_activation_packet`",
        "`skill_route_discovery_active_pass4_operator_review_dossier`",
        "`Pluviobyte/rnskill` as a generic SKILL.md\ncollection",
        "`lingbol088-spec/reverse-flow-skill` as a Codex workflow-gate skill\nroute",
        "`shepherd-agents/shepherd` as adjacent general-agent runtime\nsubstrate evidence",
        "documentation, config,\ntest, or code_patch lanes with `local_validation_required` preserved",
        "Adjacent\ngeneral-agent rows remain in `agent_harness_eval_required`",
        "rollback ref/artifact requirements",
        "grants no runtime action, external skill activation, external harness\n"
        "execution, provider launch, remote execution, promotion, or restart authority",
        "python -m pytest tests/test_skill_routing.py -q -k active_pass4_operator_activation_packet",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T062834_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260707T062834.999092Z`",
        "`skill_route_discovery_current_pass4_completion_handoff`",
        "`lingbol088-spec/reverse-flow-skill`",
        "`Pluviobyte/rnskill`",
        "documentation, config,\ntest, and code_patch as the only bounded local lanes",
        "`general_agent_recovery_workflow`",
        "`agent_harness_eval_required` fixture with runnable\nscenario, expected output, pass/fail signal, rollback artifact, and non-secret\nconfiguration fields",
        "direct code/config\nproposal, runtime action, external harness execution, provider launch, and\nremote execution remain blocked",
        "python -m pytest tests/test_skill_routing.py -q -k 20260707T062834",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T092635_pass3_proposal_replay_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T092635.428641Z`",
        "`skill_route_discovery_current_digest_20260708T092635_pass3_proposal_replay_lane`",
        "`p1-skill-route-discovery-catalog` selects the documentation lane",
        "`p2-skill-route-discovery-tests` selects the test lane",
        "`p3-agent-harness-eval-probe` remains `agent_harness_eval_required`",
        "Runtime action, external skill or\nagent activation, external harness execution",
        "python -m pytest tests/test_skill_routing.py -q -k 20260708T092635",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260707T222110_completion_handoff():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260707T222110.418015Z`",
        "`skill_route_discovery_current_pass4_completion_handoff`",
        "`Pluviobyte/rnskill` to the bounded documentation lane",
        "`lingbol088-spec/reverse-flow-skill` to the bounded test lane",
        "`NVIDIA-BioNeMo/bionemo-agent-toolkit` in the bounded test lane",
        "domain-specific skill toolkit guard before any provider, data, citation, or\n"
        "advice boundary is activated",
        "`InternScience/Agents-A1` remains queued in `general_agent_recovery_workflow`",
        "`agent_harness_eval_required`",
        "inherits no `skill_route_discovery`\nlane",
        "no direct implementation lane before local harness evaluation",
        "refs/rollback/blackhole-agent/20260708T022108Z-skill-route-discovery-pass4",
        "docs/self-model.md` stayed unchanged",
        "exports no raw source URLs, replay commands,\ntarget paths, upstream bodies",
        "python -m pytest tests/test_skill_routing.py -q -k 20260707T222110",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []


def test_skill_route_discovery_doc_records_20260708T181850_pass2_validation_lane():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "`github-growth-20260708T181850.408978Z`",
        "`skill_route_discovery_current_digest_20260708T181850_pass2_validation_lane`",
        "`p1-skill-route-discovery-reverse-flow`",
        "`p2-generic-skill-route-discovery-rnskill`",
        "`p3-agent-harness-eval-shepherd`, `p4-agent-harness-eval-hy3`, and\n"
        "`p5-agent-workflow-harness-blender-seedance`",
        "`lingbol088-spec/reverse-flow-skill` maps to the local test lane",
        "`Pluviobyte/rnskill` maps to the documentation lane",
        "`local_validation_required` true",
        "`shepherd-agents/shepherd` and `Tencent-Hunyuan/Hy3` remain adjacent\n"
        "`agent_harness_eval_required` rows",
        "The Blender/Seedance proposal stays an\noperator-visible anchor only",
        "raw source\nURLs, evidence URLs, replay commands, target paths, upstream bodies",
        "python -m pytest tests/test_skill_routing.py -q -k 20260708T181850",
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
