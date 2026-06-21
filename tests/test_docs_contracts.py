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


def test_skill_route_discovery_doc_records_bounded_matrix():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260618T062043.878926Z`",
        "`github-growth-20260618T215207.204133Z`",
        "`github-growth-20260618T233207.218276Z`",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "https://github.com/pretinhuu1-boop/threejs-game-skills",
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
        "`pass3_handoff_packet`",
        "active final-pass lane and any queued bounded lane",
        "`agent_harness_eval_after_local_corroboration` remains blocked",
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
        "`current_action`, a compact\nsupervisor row for the current scheduled pass",
        "show \"continue with the local test lane next pass\" directly at the top level",
        "`current_action_provider_runtime_preflight`",
        "`provider_runtime_preflight_sample_missing`",
        "raw\npreflight inputs, raw diagnostics, raw provider values",
        "repeats the per-profile replay checklist through\n`profile_validation_replay`",
        "`summary_signal_audit` before activation",
        "accepted, ignored, or collapsed as duplicates",
        "matched route terms, route\nprofiles, bounded proposal kinds, and hashed evidence URLs",
        "generic agent-runtime summary remains ignored by this route",
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
        "next safe action",
        "hashed hint codes",
        "denies runtime action, external skill activation,\nexternal harness execution, provider launch, remote execution",
        "\"evidence_refs\": [\"fablecodex-codex-skill-workflow\"]",
        "\"evidence_refs\": [\"https://github.com/baskduf/FableCodex\"]",
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
        "`generic_skill_workflow`",
        "These profiles are triage metadata only",
        "do not create install, scaffold, asset-generation, browser-run,\n"
        "profile-writing, provider-launch, remote-execution, or external skill activation",
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
