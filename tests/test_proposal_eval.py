import json
import shutil
from pathlib import Path

from blackhole_agent.proposal_eval import (
    build_proposal_benchmark_report,
    collect_safety_boundary_failures,
    load_proposal_replay_case,
    run_proposal_benchmark_suite,
    run_proposal_replay_case,
    run_proposal_replay_suite,
    validate_proposal_replay_manifest,
)
from blackhole_agent.proposal_synthesis import (
    build_proposal_evidence_package,
    build_route_hint_lane_map,
    build_route_hint_policy_preflight,
    classify_digest_item_route,
    review_llm_proposal_response,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "proposal_replay"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
CASE_PATHS = sorted(path for path in FIXTURE_DIR.glob("*.json") if path.name != "manifest.json")


def test_proposal_replay_suite_accepts_frozen_harness_cases():
    results = run_proposal_replay_suite(CASE_PATHS)

    assert results
    assert all(result.passed for result in results), {
        result.name: result.failures for result in results if not result.passed
    }
    assert {result.name for result in results} == {
        "agent-codex-workflow-local-validation",
        "benign-agent-harness",
        "current-wake-agent-harness-validation",
        "fastcontext-budget-memory-pressure",
        "omnigent-policy-boundary-current-wake",
        "omnigent-release-evidence-validation",
        "omnigent-route-contract",
        "public-agent-trend-validation-harness",
        "skill-route-discovery-current-window-game-frontend-lanes",
        "skill-route-discovery-four-item-lanes",
        "security-adjacent-context-pressure",
        "skill-workflow-route-discovery",
    }


def test_proposal_benchmark_suite_summarizes_frozen_harness_cases():
    report = run_proposal_benchmark_suite(CASE_PATHS)

    assert report.passed is True
    assert report.case_count == 12
    assert report.passed_count == 12
    assert report.failed_count == 0
    assert report.accepted_count == 23
    assert report.rejected_count == 11
    assert report.failure_counts == {
        "schema_validity": 0,
        "evidence_ref_constraints": 0,
        "action_lane_classification": 0,
        "validation_gate_metadata": 0,
        "safety_boundary_handling": 0,
        "other": 0,
    }
    results_by_name = {result.name: result for result in report.case_results}
    assert results_by_name["security-adjacent-context-pressure"].proposal_controls["security-boundary-review"] == {
        "kind": "follow_up_issue",
        "risk_flags": ["privacy-leakage"],
        "implementation_scope": "reviewable_proposal_only",
        "validation_gate": "privacy-leakage-human-review",
    }
    assert results_by_name["fastcontext-budget-memory-pressure"].context_budget_preflight["self_model_truncated"] is True
    assert (
        results_by_name["fastcontext-budget-memory-pressure"]
        .context_budget_preflight["evidence_truncation_uncertainty"]["missing_detail_risk"]
        is True
    )
    release = results_by_name["omnigent-release-evidence-validation"]
    assert release.proposal_validation_preflights["release-runbook-privacy-review"]["status"] == (
        "blocked_by_safety_boundary"
    )
    assert "generic-release-workflow-push" not in release.proposal_validation_preflights
    assert any(
        "generic push or untitled pull request/review evidence requires a non-generic corroborating item"
        in error
        for error in release.rejected_errors
    )
    assert (
        release.context_budget_preflight["evidence_truncation_uncertainty"]["selected_generic_push_count"]
        == 1
    )
    assert release.proposal_validation_preflights["tested-release-workflow-push"]["status"] == "ready"
    current = results_by_name["current-wake-agent-harness-validation"]
    assert current.proposal_validation_preflights["p1-local-agent-harness-validation"]["status"] == "ready"
    assert (
        current.proposal_validation_preflights["p3-benchmark-style-regression-suite"]["status"]
        == "blocked_by_safety_boundary"
    )
    boundary = results_by_name["omnigent-policy-boundary-current-wake"]
    assert boundary.proposal_controls["ask-snapshot-privacy-review"] == {
        "kind": "follow_up_issue",
        "risk_flags": ["privacy-leakage"],
        "implementation_scope": "reviewable_proposal_only",
        "validation_gate": "privacy-leakage-human-review",
    }
    assert boundary.proposal_controls["agent-tool-auth-offensive-review"] == {
        "kind": "follow_up_issue",
        "risk_flags": ["offensive-behavior"],
        "implementation_scope": "reviewable_proposal_only",
        "validation_gate": "offensive-behavior-human-review",
    }
    assert boundary.proposal_validation_preflights["mock-e2e-push-test-pattern"]["status"] == "ready"
    assert report.to_dict()["suite_name"] == "proposal-replay-benchmark"


def test_proposal_replay_manifest_validates_fixture_sources_and_cases():
    report = validate_proposal_replay_manifest(MANIFEST_PATH)

    assert report.passed is True
    assert report.case_count == 12
    assert report.fixture_names == [
        "benign-agent-harness",
        "security-adjacent-context-pressure",
        "fastcontext-budget-memory-pressure",
        "omnigent-route-contract",
        "omnigent-release-evidence-validation",
        "omnigent-policy-boundary-current-wake",
        "public-agent-trend-validation-harness",
        "current-wake-agent-harness-validation",
        "agent-codex-workflow-local-validation",
        "skill-workflow-route-discovery",
        "skill-route-discovery-four-item-lanes",
        "skill-route-discovery-current-window-game-frontend-lanes",
    ]
    assert report.evidence_urls == [
        "https://github.com/ApodexAI/AgentHarness",
        "https://github.com/LeanEntropy/threejs-phaser-game-skills",
        "https://github.com/NotPBShaw/burner-agents",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "https://github.com/microsoft/fastcontext",
        "https://github.com/omnigent-ai/omnigent",
        "https://github.com/omnigent-ai/omnigent/pull/590",
        "https://github.com/omnigent-ai/omnigent/pull/740",
        "https://github.com/omnigent-ai/omnigent/pull/779",
        "https://github.com/samarailly51-pixel/opencode-harness",
        "https://github.com/visa/visa-vulnerability-agentic-harness",
        "https://github.com/xiaoguomeiyitian/threejs-game-skills",
    ]
    assert report.to_dict()["failures"] == []


def test_proposal_replay_manifest_detects_evidence_source_drift(tmp_path):
    manifest = load_proposal_replay_case(MANIFEST_PATH)
    manifest["cases"][0]["evidence_urls"] = ["https://github.com/example/not-in-fixture"]
    for case_path in CASE_PATHS:
        shutil.copy(case_path, tmp_path / case_path.name)
    drifted_manifest = tmp_path / "manifest.json"
    drifted_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_proposal_replay_manifest(drifted_manifest)

    assert report.passed is False
    assert any("outside suite evidence" in failure for failure in report.failures)
    assert any("absent from fixture digest" in failure for failure in report.failures)


def test_proposal_replay_case_rejects_url_refs_even_when_url_is_allowed_evidence():
    case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    case["raw_response"]["proposals"][0]["evidence_refs"] = ["https://github.com/ApodexAI/AgentHarness"]
    case["expected"] = {
        "status": "rejected",
        "accepted_count": 0,
        "rejected_count": 1,
        "rejected_error_substrings": [
            "evidence_refs contain unknown item ids: https://github.com/ApodexAI/AgentHarness"
        ],
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert result.accepted_count == 0


def test_proposal_replay_case_rejects_candidate_supplied_evidence_urls():
    case = load_proposal_replay_case(FIXTURE_DIR / "public_agent_trend_validation_harness.json")
    case["raw_response"]["proposals"][0]["evidence_urls"] = ["https://github.com/example/extra"]
    case["expected"] = {
        "status": "accepted",
        "accepted_count": 1,
        "rejected_count": 2,
        "rejected_error_substrings": [
            "evidence_urls must be derived from frozen evidence_refs",
            "uncertainty must record context_budget missing_detail_risk",
        ],
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert "https://github.com/example/extra" not in {
        url
        for controls in result.proposal_controls.values()
        for url in controls.get("evidence_urls", [])
    }


def test_agent_harness_eval_fixture_enforces_json_refs_max_count_and_route_lanes():
    case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )

    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    payload = review.to_dict()
    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}
    agent_harness_policy = evidence_package["policy"]["route_hint_validation_lanes"]["agent_harness_eval"]
    p1 = next(
        candidate
        for candidate in payload["accepted_candidates"]
        if candidate["proposal_id"] == "p1-local-agent-harness-validation"
    )

    assert payload["schema_version"] == 1
    assert payload["status"] == "accepted"
    assert payload["accepted_count"] <= evidence_package["policy"]["max_proposals"]
    assert agent_harness_policy == ["documentation", "test", "code_patch"]
    assert p1["kind"] == "test"
    assert set(p1["evidence_refs"]) <= set(selected_items_by_id)
    assert all(
        "agent_harness_eval" in selected_items_by_id[item_id]["route_hints"]
        for item_id in p1["evidence_refs"]
    )
    assert p1["evidence_urls"] == sorted(
        selected_items_by_id[item_id]["source_url"] for item_id in p1["evidence_refs"]
    )

    wrong_lane_case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    wrong_lane_case["raw_response"]["proposals"] = [
        {
            **wrong_lane_case["raw_response"]["proposals"][0],
            "kind": "config",
            "proposal_id": "bad-agent-harness-config-lane",
        }
    ]
    wrong_lane_review = review_llm_proposal_response(
        json.dumps(wrong_lane_case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    assert wrong_lane_review.status == "rejected"
    assert wrong_lane_review.rejected_candidates[0]["errors"] == [
        "agent_harness_eval proposals must use one of: documentation, test, code_patch"
    ]

    url_ref_case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    url_ref_case["raw_response"]["proposals"] = [
        {
            **url_ref_case["raw_response"]["proposals"][0],
            "proposal_id": "bad-agent-harness-url-ref",
            "evidence_refs": ["https://github.com/ApodexAI/AgentHarness"],
        }
    ]
    url_ref_review = review_llm_proposal_response(
        json.dumps(url_ref_case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    assert url_ref_review.status == "rejected"
    assert "evidence_refs contain unknown item ids: https://github.com/ApodexAI/AgentHarness" in (
        url_ref_review.rejected_candidates[0]["errors"]
    )

    schema_case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    schema_case["raw_response"]["schema_version"] = 2
    schema_review = review_llm_proposal_response(
        json.dumps(schema_case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    assert schema_review.status == "rejected"
    assert schema_review.reason == "schema_version must be 1"

    too_many_case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    too_many_case["raw_response"]["proposals"] = [
        {
            **too_many_case["raw_response"]["proposals"][0],
            "proposal_id": f"agent-harness-overflow-{index}",
        }
        for index in range(evidence_package["policy"]["max_proposals"] + 1)
    ]
    too_many_review = review_llm_proposal_response(
        json.dumps(too_many_case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    assert too_many_review.status == "rejected"
    assert too_many_review.reason == "proposal count exceeds max_proposals=5"


def test_skill_route_discovery_enforces_lanes_refs_limits_and_uncertainty():
    case = load_proposal_replay_case(FIXTURE_DIR / "skill_workflow_route_discovery.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )
    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}

    assert evidence_package["policy"]["route_hint_validation_lanes"]["skill_route_discovery"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert {
        route_hint
        for item in selected_items_by_id.values()
        for route_hint in item["route_hints"]
    } == {"skill_route_discovery"}
    preflight = build_route_hint_policy_preflight(evidence_package)
    assert preflight["ok"] is True
    assert preflight["route_hint_count"] == 1
    assert preflight["selected_route_hints"] == ["skill_route_discovery"]
    assert preflight["configured_route_hints"] == [
        "agent_harness_eval",
        "governance_policy",
        "provider_config_preflight",
        "skill_route_discovery",
    ]
    assert preflight["skill_route_discovery_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["allowed_skill_route_discovery_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["governance_policy_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["allowed_governance_policy_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["diagnostics"] == []
    implementation_preflight = preflight["skill_route_implementation_preflight"]
    assert implementation_preflight["controller_surface"] == "skill_route_implementation_preflight"
    assert implementation_preflight["status"] == "ready"
    assert implementation_preflight["candidate_count"] == 2
    assert implementation_preflight["ready_candidate_count"] == 2
    assert implementation_preflight["blocked_candidate_count"] == 0
    assert implementation_preflight["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert implementation_preflight["truncated_item_ids_blocked_as_evidence_refs"] is True
    assert implementation_preflight["runtime_action"] == "none"
    assert implementation_preflight["external_skill_activation_allowed"] is False
    assert [row["selected_local_lane"] for row in implementation_preflight["rows"]] == ["test", "config"]
    assert all(row["implementation_route_allowed"] is True for row in implementation_preflight["rows"])
    assert all(row["truncated_item_id_ref_allowed"] is False for row in implementation_preflight["rows"])

    valid_proposal = case["raw_response"]["proposals"][0]
    table = [
        (
            "accepts_allowed_lane",
            {**valid_proposal, "kind": "test", "proposal_id": "skill-route-test-lane"},
            "accepted",
            None,
        ),
        (
            "rejects_escaped_lane",
            {**valid_proposal, "kind": "follow_up_issue", "proposal_id": "skill-route-follow-up-lane"},
            "rejected",
            "skill_route_discovery proposals must use one of: documentation, config, test, code_patch",
        ),
        (
            "rejects_url_ref",
            {
                **valid_proposal,
                "proposal_id": "skill-route-url-ref",
                "evidence_refs": ["https://github.com/baskduf/FableCodex"],
            },
            "rejected",
            "evidence_refs contain unknown item ids: https://github.com/baskduf/FableCodex",
        ),
    ]

    for name, proposal, expected_status, expected_error in table:
        review = review_llm_proposal_response(
            json.dumps({**case["raw_response"], "proposals": [proposal]}),
            evidence_package,
            mode=case["mode"],
        )

        assert review.status == expected_status, name
        if expected_error is None:
            accepted = review.accepted_candidates[0]
            assert accepted["proposal_id"] == proposal["proposal_id"]
            assert accepted["evidence_urls"] == sorted(
                selected_items_by_id[item_id]["source_url"] for item_id in accepted["evidence_refs"]
            )
        else:
            assert expected_error in review.rejected_candidates[0]["errors"]

    too_many_review = review_llm_proposal_response(
        json.dumps(
            {
                **case["raw_response"],
                "proposals": [
                    {**valid_proposal, "proposal_id": f"skill-route-overflow-{index}"}
                    for index in range(evidence_package["policy"]["max_proposals"] + 1)
                ],
            }
        ),
        evidence_package,
        mode=case["mode"],
    )
    assert too_many_review.status == "rejected"
    assert too_many_review.reason == "proposal count exceeds max_proposals=5"

    truncation_case = load_proposal_replay_case(FIXTURE_DIR / "skill_workflow_route_discovery.json")
    truncation_case["options"] = {"max_items": 1, "max_item_text_chars": 360}
    truncation_package = build_proposal_evidence_package(
        truncation_case["digest"],
        max_items=truncation_case["options"]["max_items"],
        max_item_text_chars=truncation_case["options"]["max_item_text_chars"],
    )
    assert truncation_package["context_budget"]["evidence_truncation_uncertainty"]["missing_detail_risk"] is True
    assert truncation_package["context_budget"]["selected_item_ids"] == ["fablecodex-codex-skill-workflow"]
    assert truncation_package["context_budget"]["truncated_item_ids"] == ["compass-skills-task-routing"]
    truncation_preflight = build_route_hint_policy_preflight(truncation_package)[
        "skill_route_implementation_preflight"
    ]
    assert truncation_preflight["status"] == "ready"
    assert truncation_preflight["selected_item_ids"] == ["fablecodex-codex-skill-workflow"]
    assert truncation_preflight["truncated_item_ids"] == ["compass-skills-task-routing"]
    assert truncation_preflight["truncated_item_ids_blocked_as_evidence_refs"] is True
    assert [row["item_id"] for row in truncation_preflight["rows"]] == ["fablecodex-codex-skill-workflow"]

    truncated_ref_review = review_llm_proposal_response(
        json.dumps(
            {
                **truncation_case["raw_response"],
                "proposals": [
                    {
                        **valid_proposal,
                        "proposal_id": "skill-route-truncated-ref",
                        "evidence_refs": ["compass-skills-task-routing"],
                        "uncertainty": "This malformed candidate cites omitted context-budget evidence.",
                    }
                ],
            }
        ),
        truncation_package,
        mode=truncation_case["mode"],
    )
    assert truncated_ref_review.status == "rejected"
    assert "evidence_refs contain unknown item ids: compass-skills-task-routing" in (
        truncated_ref_review.rejected_candidates[0]["errors"]
    )

    missing_uncertainty_review = review_llm_proposal_response(
        json.dumps(
            {
                **truncation_case["raw_response"],
                "proposals": [
                    {
                        **valid_proposal,
                        "proposal_id": "skill-route-missing-detail-risk",
                        "evidence_refs": ["fablecodex-codex-skill-workflow"],
                        "uncertainty": "The selected repository summary supports this local routing test.",
                    }
                ],
            }
        ),
        truncation_package,
        mode=truncation_case["mode"],
    )
    assert missing_uncertainty_review.status == "rejected"
    assert "uncertainty must record context_budget missing_detail_risk" in (
        missing_uncertainty_review.rejected_candidates[0]["errors"]
    )


def test_skill_route_discovery_four_item_fixture_stays_in_bounded_lanes():
    case = load_proposal_replay_case(FIXTURE_DIR / "skill_route_discovery_four_item_lanes.json")
    result = run_proposal_replay_case(case)
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )
    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}
    selected_item_ids = set(evidence_package["context_budget"]["selected_item_ids"])
    truncated_item_ids = set(evidence_package["context_budget"]["truncated_item_ids"])
    accepted_kinds = {controls["kind"] for controls in result.proposal_controls.values()}

    assert result.passed is True
    assert result.selected_item_ids == [
        "fablecodex-workflow-skill-eval",
        "threejs-game-skills-domain-director",
        "compass-skills-local-lanes",
        "threejs-game-skills-fork-lineage",
    ]
    assert result.truncated_item_ids == []
    assert accepted_kinds == {"documentation", "config", "test", "code_patch"}
    assert set(result.proposal_controls) == {
        "p1-skill-route-doc-lane",
        "p2-skill-route-config-lane",
        "p3-skill-route-test-lane",
        "p4-skill-route-code-patch-lane",
    }
    assert all(
        controls["implementation_scope"] == "local_validation_candidate"
        and controls["validation_gate"] == "focused-evidence-review"
        for controls in result.proposal_controls.values()
    )
    assert all(
        "skill_route_discovery" in item["route_hints"]
        for item in selected_items_by_id.values()
    )

    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    assert review.status == "accepted"
    for candidate in review.accepted_candidates:
        refs = set(candidate["evidence_refs"])
        assert refs <= selected_item_ids
        assert not refs & truncated_item_ids
        assert candidate["kind"] in {"documentation", "config", "test", "code_patch"}
        assert "evidence_urls" not in next(
            raw
            for raw in case["raw_response"]["proposals"]
            if raw["proposal_id"] == candidate["proposal_id"]
        )
        assert candidate["evidence_urls"] == sorted(
            selected_items_by_id[item_id]["source_url"] for item_id in candidate["evidence_refs"]
        )
    assert "skill_route_discovery proposals must use one of: documentation, config, test, code_patch" in (
        review.rejected_candidates[0]["errors"]
    )

    url_expansion_case = load_proposal_replay_case(FIXTURE_DIR / "skill_route_discovery_four_item_lanes.json")
    url_expansion_case["raw_response"]["proposals"] = [
        {
            **url_expansion_case["raw_response"]["proposals"][0],
            "proposal_id": "skill-route-candidate-supplied-url",
            "evidence_urls": ["https://github.com/example/extra-skill-route"],
        }
    ]
    url_expansion_review = review_llm_proposal_response(
        json.dumps(url_expansion_case["raw_response"]),
        evidence_package,
        mode=url_expansion_case["mode"],
    )
    assert url_expansion_review.status == "rejected"
    assert any(
        "evidence_urls must be derived from frozen evidence_refs" in error
        for error in url_expansion_review.rejected_candidates[0]["errors"]
    )


def test_route_hint_lane_map_is_bounded_metadata_only_for_skill_discovery():
    case = load_proposal_replay_case(FIXTURE_DIR / "skill_workflow_route_discovery.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )

    lane_map = build_route_hint_lane_map(evidence_package)
    skill_entry = next(
        entry
        for entry in lane_map["route_hint_entries"]
        if entry["route_hint"] == "skill_route_discovery"
    )

    assert lane_map["ok"] is True
    assert lane_map["allowed_proposal_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert lane_map["route_class_counts"] == {"skill_workflow": 2}
    assert [row["route_class"] for row in lane_map["route_classifier"]] == [
        "skill_workflow",
        "skill_workflow",
    ]
    assert all(
        row["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
        for row in lane_map["route_classifier"]
    )
    assert lane_map["permission_effect"] == "none"
    assert lane_map["evidence_url_effect"] == "none"
    assert lane_map["runtime_action"] == "none"
    assert lane_map["route_activity_pressure"] == {
        "controller_surface": "skill_route_activity_pressure",
        "repeated_project_count": 0,
        "repeated_projects": [],
        "allowed_lanes": ["documentation", "config", "test", "code_patch"],
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }
    assert skill_entry["validation_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert [lane["proposal_kind"] for lane in skill_entry["proposal_lanes"]] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    implementation_preflight = lane_map["skill_route_implementation_preflight"]
    assert implementation_preflight["status"] == "ready"
    assert implementation_preflight["decision"] == "select_bounded_local_lane_before_implementation"
    assert implementation_preflight["candidate_count"] == 2
    assert [row["selected_local_lane"] for row in implementation_preflight["rows"]] == ["test", "config"]
    assert [row["queued_local_lanes"] for row in implementation_preflight["rows"]] == [
        ["documentation", "config", "code_patch"],
        ["documentation", "test", "code_patch"],
    ]
    assert all(row["evidence_ref_scope"] == "selected_item_ids_only" for row in implementation_preflight["rows"])
    assert all(lane["runtime_action"] == "none" for lane in skill_entry["proposal_lanes"])
    assert all(lane["local_validation_required"] is True for lane in skill_entry["proposal_lanes"])
    assert "allowed_evidence_urls" not in lane_map
    assert "permissions" not in lane_map


def test_route_hint_lane_map_exposes_current_pass3_skill_route_handoff():
    digest = {
        "digest_id": "github-growth-20260624T095356.034961Z",
        "generated_at": "2026-06-24T09:53:56.034961Z",
        "items": [
            {
                "item_id": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "COMPASS Skills personal alignment skills system for AI agents with SKILL.md "
                    "task clarification, repo-local task memory, handoff prompts, and profile workflows."
                ),
                "relevance_reason": "Skill workflow repository evidence maps to bounded local skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.84,
            },
            {
                "item_id": "zhengxi-views",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Agent Skill repository with SKILL.md, references, scripts, source-cited corpus search, "
                    "and domain research workflow constraints."
                ),
                "relevance_reason": "Source-cited skill workflow evidence should stay in bounded local lanes.",
                "risk_flags": [],
                "confidence": 0.83,
            },
            {
                "item_id": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Codex and Claude Code skills for Three.js browser game workflows, director routing, "
                    "gameplay, graphics, UI, QA, and release checks."
                ),
                "relevance_reason": "Game skill workflow evidence maps to bounded local skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.82,
            },
            {
                "item_id": "omnigent-general-agent",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Omnigent open-source AI agent framework and meta-harness for orchestrating agent "
                    "runtimes, policies, sandboxing, and real-time collaboration."
                ),
                "relevance_reason": (
                    "General agent project evidence requires agent_harness_eval validation, not skill "
                    "discovery inheritance."
                ),
                "risk_flags": [],
                "confidence": 0.81,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=360)
    for item in evidence_package["items"]:
        item["implementation_scope"] = "reviewable_proposal_only"
        item["validation_gate"] = "candidate-supplied-gate"

    lane_map = build_route_hint_lane_map(evidence_package)
    handoff = lane_map["skill_route_pass3_handoff"]

    assert lane_map["ok"] is True
    assert lane_map["route_class_counts"] == {"general_agent_project": 1, "skill_workflow": 3}
    assert handoff["controller_surface"] == "skill_route_discovery_pass3_handoff"
    assert handoff["status"] == "ready"
    assert handoff["capability_pass"] == "3_of_4"
    assert handoff["skill_workflow_item_ids"] == [
        "compass-skills",
        "zhengxi-views",
        "threejs-game-skills",
    ]
    assert handoff["general_agent_project_item_ids"] == ["omnigent-general-agent"]
    assert set(handoff["selected_item_ids"]) == {
        "compass-skills",
        "zhengxi-views",
        "threejs-game-skills",
        "omnigent-general-agent",
    }
    assert handoff["evidence_ref_scope"] == "selected_item_ids_only"
    assert handoff["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert handoff["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert handoff["skill_route_lane_limit_reaffirmed"] is True
    assert handoff["general_agent_eval_split_reaffirmed"] is True
    assert handoff["final_scope"] == "pending_agent_harness_eval"
    assert handoff["validation_gates"] == [
        "agent_harness_eval_before_implementation_route",
        "focused-evidence-review",
        "local_frontend_validation_before_game_skill_activation",
        "state_handoff_boundary_before_profile_or_memory_write",
    ]
    recomputed = handoff["controller_recomputed"]
    assert recomputed["controller_surface"] == "skill_route_discovery_pass3_controller_recomputed_scope_gate"
    assert recomputed["recomputed_from"] == "route_classification_and_route_hints"
    assert recomputed["proposal_text_scope_trusted"] is False
    assert recomputed["proposal_text_validation_gate_trusted"] is False
    assert recomputed["evidence_ref_scope"] == "selected_item_ids_only"
    assert recomputed["agent_harness_eval_required_item_ids"] == ["omnigent-general-agent"]
    assert "omnigent-general-agent:agent_harness_eval_required_before_implementation" in recomputed["diagnostics"]
    recomputed_rows = {row["item_id"]: row for row in recomputed["rows"]}
    assert recomputed_rows["compass-skills"]["final_scope"] == "local_validation_candidate"
    assert recomputed_rows["compass-skills"]["selected_local_lane"] == "config"
    assert recomputed_rows["compass-skills"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert recomputed_rows["zhengxi-views"]["final_scope"] == "local_validation_candidate"
    assert recomputed_rows["zhengxi-views"]["validation_gates"] == ["focused-evidence-review"]
    assert recomputed_rows["threejs-game-skills"]["final_scope"] == "local_validation_candidate"
    assert recomputed_rows["threejs-game-skills"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert recomputed_rows["omnigent-general-agent"]["final_scope"] == "pending_agent_harness_eval"
    assert recomputed_rows["omnigent-general-agent"]["validation_gates"] == [
        "agent_harness_eval_before_implementation_route"
    ]
    assert all(row["proposal_text_scope_ignored"] is True for row in recomputed["rows"])
    assert all(row["proposal_text_validation_gate_ignored"] is True for row in recomputed["rows"])
    assert all(row["evidence_ref_scope"] == "selected_item_ids_only" for row in recomputed["rows"])
    assert handoff["local_validation_required"] is True
    assert handoff["runtime_action"] == "none"
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["external_agent_activation_allowed"] is False
    assert handoff["external_harness_execution_allowed"] is False
    assert handoff["raw_source_url_export_allowed"] is False
    assert handoff["upstream_body_export_allowed"] is False
    assert all(
        set(row["local_lanes"]) <= {"documentation", "config", "test", "code_patch"}
        for row in handoff["skill_route_rows"]
    )
    assert handoff["general_agent_rows"] == [
        {
            "item_id": "omnigent-general-agent",
            "route_class": "general_agent_project",
            "primary_route": "agent_harness_eval_required",
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "skill_route_discovery_inherited": False,
            "local_validation_required": True,
            "runtime_action": "none",
        }
    ]


def test_route_hint_lane_map_exposes_pass2_activation_readiness_for_current_skill_window():
    digest = {
        "digest_id": "github-growth-20260628T112729-pass2-skill-route-discovery",
        "generated_at": "2026-06-28T11:27:29Z",
        "items": [
            {
                "item_id": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "COMPASS Skills personal alignment skills system for AI agents with SKILL.md "
                    "task clarification, local memory, handoff prompts, and collaboration profiles."
                ),
                "relevance_reason": "Skill ecosystem handoff evidence maps to bounded config and test lanes.",
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "zhengxi-views",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "zhengxi-views source-cited investment research Agent Skill with evidence-backed "
                    "question answering and no fabrication claims."
                ),
                "relevance_reason": "Source-cited skill evidence should stay in bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.83,
            },
            {
                "item_id": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Codex and Claude Code skills for Three.js browser game workflows, director routing, "
                    "gameplay, graphics, UI, QA, and scaffold helpers."
                ),
                "relevance_reason": "Game skill workflow evidence maps to bounded local skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.82,
            },
            {
                "item_id": "qwen-agentworld",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Qwen-AgentWorld language world models for general agents with benchmark and "
                    "agent-environment evaluation claims."
                ),
                "relevance_reason": (
                    "General agent project evidence requires agent_harness_eval validation before "
                    "any implementation lane."
                ),
                "risk_flags": [],
                "confidence": 0.8,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)

    lane_map = build_route_hint_lane_map(evidence_package)
    readiness = lane_map["current_pass2_activation_readiness"]

    assert lane_map["route_class_counts"] == {"general_agent_project": 1, "skill_workflow": 3}
    assert readiness["controller_surface"] == "skill_route_discovery_pass2_activation_readiness"
    assert readiness["status"] == "blocked"
    assert readiness["capability_pass"] == "2_of_4"
    assert readiness["active_proposal_ids"] == [
        "p1-skill-route-discovery-compass-zhengxi",
        "p2-threejs-game-skill-workflow-doc",
        "p3-agent-harness-eval-general-agent-projects",
    ]
    assert readiness["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert readiness["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert readiness["blocked_general_agent_item_ids"] == ["qwen-agentworld"]
    assert all(row["local_validation_required"] is True for row in readiness["skill_route_rows"])
    assert all(row["implementation_route_allowed"] is True for row in readiness["skill_route_rows"])
    assert all(
        set(row["allowed_local_lanes"]) <= {"documentation", "config", "test", "code_patch"}
        for row in readiness["skill_route_rows"]
    )
    assert readiness["general_agent_rows"] == [
        {
            "item_id": "qwen-agentworld",
            "route_class": "general_agent_project",
            "primary_route": "agent_harness_eval_required",
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "implementation_lanes_enabled": False,
            "selected_implementation_lanes": [],
            "blocked_until": "local_agent_harness_evaluation_result",
            "skill_route_discovery_inherited": False,
            "local_validation_required": True,
            "runtime_action": "none",
        }
    ]
    assert readiness["external_skill_activation_allowed"] is False
    assert readiness["external_agent_activation_allowed"] is False
    assert readiness["external_harness_execution_allowed"] is False
    assert readiness["raw_source_url_export_allowed"] is False


def test_route_classifier_does_not_treat_negated_skill_inheritance_as_skill_signal():
    classification = classify_digest_item_route(
        {
            "event_kind": "RepositoryTrend",
            "summary": (
                "omnigent-ai/omnigent: general AI agent framework and meta-harness with policy, "
                "sandboxing, and runtime orchestration."
            ),
            "relevance_reason": "General agent movement requires harness evaluation, not skill discovery inheritance.",
        }
    )

    assert classification["route_class"] == "general_agent_project"
    assert classification["route_hints"] == ["agent_harness_eval", "governance_policy"]
    assert classification["allowed_lanes"] == []
    assert classification["evaluation_lane"] == "agent_harness_eval_required"


def test_skill_route_profile_classifies_phaser_game_engine_evidence_as_frontend_workflow():
    classification = classify_digest_item_route(
        {
            "event_kind": "RepositoryTrend",
            "summary": (
                "LeanEntropy/threejs-phaser-game-skills: agent skills for Phaser game engine "
                "browser workflows, QA checks, and scaffold materials."
            ),
            "relevance_reason": (
                "Supports bounded skill_route_discovery lanes for game frontend workflow validation."
            ),
        }
    )

    assert classification["route_class"] == "skill_workflow"
    assert classification["route_hints"] == ["skill_route_discovery"]
    assert classification["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert classification["route_profiles"] == ["game_frontend_workflow"]
    assert classification["runtime_action"] == "none"
    assert classification["local_validation_required"] is True


def test_skill_route_discovery_policy_preflight_blocks_unbounded_route_config():
    case = load_proposal_replay_case(FIXTURE_DIR / "skill_workflow_route_discovery.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )
    evidence_package["policy"]["route_hint_validation_lanes"]["skill_route_discovery"] = [
        "documentation",
        "config",
        "test",
        "code_patch",
        "runtime_execution",
    ]

    lane_map = build_route_hint_lane_map(evidence_package)
    preflight = build_route_hint_policy_preflight(evidence_package)
    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )

    skill_entry = next(
        entry
        for entry in lane_map["route_hint_entries"]
        if entry["route_hint"] == "skill_route_discovery"
    )
    assert lane_map["ok"] is False
    assert skill_entry["unsupported_lanes"] == ["runtime_execution"]
    assert [lane["proposal_kind"] for lane in skill_entry["proposal_lanes"]] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert preflight["ok"] is False
    assert preflight["diagnostics"] == [
        "skill_route_discovery route hint must resolve only to: documentation, config, test, code_patch",
        "skill_route_discovery has unsupported lanes: runtime_execution",
    ]
    assert review.status == "rejected"
    assert review.reason == (
        "route_hint_policy_preflight failed: "
        "skill_route_discovery route hint must resolve only to: documentation, config, test, code_patch; "
        "skill_route_discovery has unsupported lanes: runtime_execution"
    )


def test_skill_route_discovery_policy_preflight_blocks_item_level_lane_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "skill_workflow_route_discovery.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )
    evidence_package["items"][0]["route_classification"]["allowed_lanes"] = [
        "documentation",
        "config",
        "test",
        "code_patch",
        "runtime_execution",
    ]

    lane_map = build_route_hint_lane_map(evidence_package)
    preflight = build_route_hint_policy_preflight(evidence_package)
    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )

    drift_row = next(
        row
        for row in lane_map["route_classifier"]
        if row["item_id"] == evidence_package["items"][0]["item_id"]
    )
    candidate_row = next(
        row
        for row in lane_map["skill_route_local_lane_candidates"]["rows"]
        if row["item_id"] == evidence_package["items"][0]["item_id"]
    )

    assert lane_map["ok"] is False
    assert lane_map["diagnostics"] == [
        f"{evidence_package['items'][0]['item_id']} skill_route_discovery item has unsupported lanes: runtime_execution"
    ]
    assert drift_row["unsupported_lanes"] == ["runtime_execution"]
    assert candidate_row["local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert candidate_row["unsupported_lanes"] == ["runtime_execution"]
    assert candidate_row["lanes_bounded"] is False
    assert candidate_row["lane_status"] == "blocked_unsupported_lanes"
    implementation_preflight = lane_map["skill_route_implementation_preflight"]
    assert implementation_preflight["status"] == "blocked"
    assert implementation_preflight["decision"] == "block_skill_route_implementation_until_lanes_are_bounded"
    assert implementation_preflight["blocked_candidate_count"] == 1
    assert implementation_preflight["activation_blockers"] == [
        f"{evidence_package['items'][0]['item_id']}:unsupported_skill_route_lanes"
    ]
    assert implementation_preflight["rows"][0]["implementation_route_allowed"] is False
    assert implementation_preflight["rows"][0]["unsupported_lanes"] == ["runtime_execution"]
    assert lane_map["skill_route_local_lane_candidates"]["unsupported_lane_count"] == 1
    assert lane_map["skill_route_local_lane_candidates"]["activation_gate"] == "blocked_before_activation"
    assert preflight["ok"] is False
    assert preflight["diagnostics"] == lane_map["diagnostics"]
    assert review.status == "rejected"
    assert review.reason == "route_hint_policy_preflight failed: " + lane_map["diagnostics"][0]


def test_omnigent_governance_policy_hint_bounds_local_validation_lanes():
    case = load_proposal_replay_case(FIXTURE_DIR / "omnigent_route_contract.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )
    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}

    assert "governance_policy" in selected_items_by_id["omnigent-trend"]["route_hints"]
    assert evidence_package["policy"]["route_hint_validation_lanes"]["governance_policy"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    preflight = build_route_hint_policy_preflight(evidence_package)
    assert preflight["ok"] is True
    assert "governance_policy" in preflight["selected_route_hints"]
    assert preflight["governance_policy_lanes"] == ["documentation", "config", "test", "code_patch"]

    valid_proposal = case["raw_response"]["proposals"][0]
    allowed_review = review_llm_proposal_response(
        json.dumps(
            {
                **case["raw_response"],
                "proposals": [
                    {
                        **valid_proposal,
                        "proposal_id": "omnigent-governance-documentation-lane",
                        "kind": "documentation",
                        "evidence_refs": ["omnigent-trend"],
                    }
                ],
            }
        ),
        evidence_package,
        mode=case["mode"],
    )
    assert allowed_review.status == "accepted"

    escaped_review = review_llm_proposal_response(
        json.dumps(
            {
                **case["raw_response"],
                "proposals": [
                    {
                        **valid_proposal,
                        "proposal_id": "omnigent-governance-follow-up-lane",
                        "kind": "follow_up_issue",
                        "evidence_refs": ["omnigent-trend"],
                    }
                ],
            }
        ),
        evidence_package,
        mode=case["mode"],
    )
    assert escaped_review.status == "rejected"
    assert "governance_policy proposals must use one of: documentation, config, test, code_patch" in (
        escaped_review.rejected_candidates[0]["errors"]
    )


def test_proposal_benchmark_report_classifies_schema_and_evidence_ref_drift():
    schema_case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    schema_case["raw_response"]["schema_version"] = 2
    schema_case["expected"] = {"status": "accepted", "accepted_count": 1}
    evidence_case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    evidence_case["raw_response"]["proposals"][0]["evidence_refs"] = [
        "https://github.com/ApodexAI/AgentHarness"
    ]
    evidence_case["expected"] = {"status": "accepted", "accepted_count": 1}

    report = build_proposal_benchmark_report([schema_case, evidence_case])

    assert report.passed is False
    assert report.failed_count == 2
    assert report.failure_counts["schema_validity"] == 2
    assert report.failure_counts["evidence_ref_constraints"] == 1


def test_proposal_replay_case_detects_control_classification_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "security_adjacent_context_pressure.json")
    case["expected"]["proposal_controls"]["security-boundary-review"]["implementation_scope"] = (
        "local_validation_candidate"
    )

    result = run_proposal_replay_case(case)

    assert result.passed is False
    assert any("expected proposal_controls" in failure for failure in result.failures)


def test_proposal_benchmark_report_classifies_action_lane_and_safety_boundary_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "security_adjacent_context_pressure.json")
    case["expected"]["proposal_controls"]["security-boundary-review"] = {
        "kind": "test",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "focused-evidence-review",
    }

    report = build_proposal_benchmark_report([case])

    assert report.passed is False
    assert report.failure_counts["action_lane_classification"] == 1
    assert report.failure_counts["safety_boundary_handling"] == 1


def test_proposal_replay_case_detects_boundary_gate_drift():
    failures = collect_safety_boundary_failures(
        "wrong-boundary-gate",
        {
            "ask-snapshot-privacy-review": {
                "kind": "follow_up_issue",
                "risk_flags": ["privacy-leakage"],
                "implementation_scope": "reviewable_proposal_only",
                "validation_gate": "offensive-behavior-human-review",
            }
        },
    )

    assert failures == [
        "wrong-boundary-gate: safety boundary proposal ask-snapshot-privacy-review "
        "must use validation_gate='privacy-leakage-human-review'"
    ]


def test_proposal_benchmark_report_classifies_validation_gate_metadata_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    case["expected"]["proposal_validation_preflights"]["p1-local-agent-harness-validation"]["status"] = (
        "validation_gap"
    )

    report = build_proposal_benchmark_report([case])

    assert report.passed is False
    assert report.failure_counts["validation_gate_metadata"] == 1


def test_omnigent_replay_marks_missing_test_coverage_validation_as_gap_not_safety_block():
    case = load_proposal_replay_case(FIXTURE_DIR / "omnigent_route_contract.json")
    case["raw_response"]["proposals"][0]["validation_task"] = (
        "Validate locally that the metadata remains replayable before implementation."
    )
    case["expected"]["proposal_validation_preflights"] = {
        "validation-route-contract": {
            "status": "validation_gap",
            "requires_unit_test_or_coverage": True,
            "has_unit_test_signal": False,
            "has_coverage_signal": False,
            "validation_gaps": ["missing_unit_test_or_coverage_validation"],
            "safety_block": False,
            "blocks_autonomous_apply": False,
        }
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert result.proposal_controls["validation-route-contract"]["implementation_scope"] == (
        "local_validation_candidate"
    )
    assert result.proposal_validation_preflights["validation-route-contract"]["status"] == "validation_gap"


def test_omnigent_growth_interpretation_review_has_stable_json_contract():
    case = load_proposal_replay_case(FIXTURE_DIR / "omnigent_route_contract.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )

    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    payload = review.to_dict()

    assert list(payload) == [
        "schema_version",
        "mode",
        "status",
        "reason",
        "input_digest_id",
        "input_hash",
        "output_hash",
        "accepted_count",
        "rejected_count",
        "accepted_candidates",
        "rejected_candidates",
        "interpretation",
        "self_model_reading",
    ]
    assert payload["schema_version"] == 1
    assert payload["mode"] == "hybrid"
    assert payload["status"] == "accepted"
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["interpretation"] == {
        "run_interpretation": case["raw_response"]["run_interpretation"],
        "rejected_items": [],
    }
    assert payload["self_model_reading"] == {"status": "unchanged"}

    accepted = payload["accepted_candidates"][0]
    assert list(accepted) == [
        "proposal_id",
        "kind",
        "summary",
        "evidence_refs",
        "evidence_urls",
        "rule_risk_flags",
        "added_risk_flags",
        "validation_task",
        "rationale",
        "uncertainty",
        "self_effect",
        "action_lane",
    ]
    assert accepted["proposal_id"] == "validation-route-contract"
    assert accepted["evidence_refs"] == case["expected"]["accepted_evidence_refs"]["validation-route-contract"]

    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}
    assert set(accepted["evidence_refs"]) <= set(selected_items_by_id)
    assert accepted["evidence_urls"] == sorted(
        {
            selected_items_by_id[item_id]["source_url"]
            for item_id in accepted["evidence_refs"]
        }
    )

    missing_detail = evidence_package["context_budget"]["evidence_truncation_uncertainty"]
    assert missing_detail["missing_detail_risk"] is True
    assert "generic" in accepted["uncertainty"].lower()
    assert "specific upstream implementation" in accepted["uncertainty"].lower()

    rejected = payload["rejected_candidates"][0]
    assert rejected["candidate"]["proposal_id"] == "underspecified-growth-route"
    assert "rationale must not be empty" in rejected["errors"]
    assert "uncertainty must not be empty" in rejected["errors"]
