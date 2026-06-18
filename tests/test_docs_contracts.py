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


def test_architecture_links_upstream_evidence_interpretation_contract():
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "docs/upstream-evidence-interpretation.md" in architecture
    assert "not permission or implementation authority" in architecture
    assert "low-detail PR/push interpretation rule" in architecture
    assert "docs/skill-route-discovery.md" in architecture
    assert "classification-only matrix" in architecture


def test_skill_route_discovery_doc_records_bounded_matrix():
    doc = (REPO_ROOT / "docs" / "skill-route-discovery.md").read_text(encoding="utf-8")

    required_phrases = [
        "source digest `github-growth-20260618T062043.878926Z`",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "No upstream code, install scripts, prompts, or skill bodies were adopted.",
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
    ]

    missing = [phrase for phrase in required_phrases if phrase not in doc]

    assert missing == []
