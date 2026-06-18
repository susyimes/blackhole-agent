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


def test_skill_route_discovery_doc_records_bounded_matrix():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260618T062043.878926Z`",
        "`github-growth-20260618T215207.204133Z`",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/majidmanzarpour/threejs-game-skills",
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
        "\"evidence_refs\": [\"fablecodex-codex-skill-workflow\"]",
        "\"evidence_refs\": [\"https://github.com/baskduf/FableCodex\"]",
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
