import json
from pathlib import Path

from blackhole_agent.skill_routing import (
    AMBIGUOUS_SKILL_MATCH,
    EXACT_TRIGGER_MATCH,
    SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
    SKILL_ROUTE_DISCOVERY_DISABLED,
    SKILL_ROUTE_DISCOVERY_INVALID,
    SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
    SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES,
    NO_SKILL_MATCH,
    ExternalSkillRouteCandidate,
    ExternalSkillEvidenceItem,
    ExternalSkillRepositorySummary,
    TOPICAL_MATCH,
    SkillDescriptor,
    build_skill_route_discovery_proposal_lane_map,
    build_skill_route_discovery_registry,
    build_skill_route_discovery_registry_from_evidence_items,
    build_skill_route_discovery_registry_from_summaries,
    build_skill_routing_index,
    rank_skills_for_task,
    select_skill_for_task,
)


def test_exact_trigger_match_dominates_validated_topical_match():
    skills = [
        SkillDescriptor(
            name="task-clarifier",
            trigger_terms=("$task-clarifier",),
            domains=("planning", "scope"),
            validation_status="experimental",
        ),
        SkillDescriptor(
            name="planning-guide",
            domains=("planning",),
            validation_status="validated",
        ),
    ]

    ranked = rank_skills_for_task("Use $task-clarifier before planning this migration.", skills)

    assert [decision.descriptor.name for decision in ranked] == ["task-clarifier", "planning-guide"]
    assert ranked[0].route == EXACT_TRIGGER_MATCH
    assert ranked[0].reasons == ("trigger:$task-clarifier", "validation:experimental")
    assert ranked[1].route == TOPICAL_MATCH


def test_explicit_skill_name_match_dominates_generic_workflow_domain():
    skills = [
        SkillDescriptor(
            name="task-forest",
            domains=("task graph", "workflow"),
            validation_status="experimental",
        ),
        SkillDescriptor(
            name="workflow-router",
            domains=("workflow",),
            validation_status="validated",
        ),
    ]

    ranked = rank_skills_for_task("Use task-forest to preserve this workflow history.", skills)

    assert [decision.descriptor.name for decision in ranked] == ["task-forest", "workflow-router"]
    assert ranked[0].route == EXACT_TRIGGER_MATCH
    assert ranked[0].reasons == ("skill_name:task-forest", "validation:experimental")
    assert ranked[1].route == TOPICAL_MATCH


def test_at_prefixed_skill_name_counts_as_explicit_invocation():
    skills = [
        SkillDescriptor(name="codex-fable5", domains=("workflow",), validation_status="experimental"),
        SkillDescriptor(name="workflow-router", domains=("workflow",), validation_status="validated"),
    ]

    ranked = rank_skills_for_task("@codex-fable5 run the strict workflow gate.", skills)

    assert [decision.descriptor.name for decision in ranked] == ["codex-fable5", "workflow-router"]
    assert ranked[0].route == EXACT_TRIGGER_MATCH
    assert ranked[0].reasons == ("skill_name:codex-fable5", "validation:experimental")


def test_topical_matches_are_ranked_by_validation_status_then_name():
    skills = [
        SkillDescriptor(name="workflow-beta", domains=("workflow",), validation_status="experimental"),
        SkillDescriptor(name="workflow-alpha", domains=("workflow",), validation_status="validated"),
        SkillDescriptor(name="workflow-zeta", domains=("workflow",), validation_status="validated"),
    ]

    ranked = rank_skills_for_task("Improve workflow routing for local agent tasks.", skills)

    assert [decision.descriptor.name for decision in ranked] == [
        "workflow-alpha",
        "workflow-zeta",
        "workflow-beta",
    ]
    assert all(decision.route == TOPICAL_MATCH for decision in ranked)
    assert ranked[0].score == ranked[1].score


def test_no_match_cases_are_deterministic_and_can_be_filtered():
    skills = [
        SkillDescriptor(name="zeta", trigger_terms=("$zeta",), domains=("release",), validation_status="validated"),
        SkillDescriptor(name="alpha", trigger_terms=("$alpha",), domains=("memory",), validation_status="unknown"),
    ]

    ranked = rank_skills_for_task("Summarize repository files.", skills)
    filtered = rank_skills_for_task("Summarize repository files.", skills, include_no_match=False)

    assert [decision.descriptor.name for decision in ranked] == ["zeta", "alpha"]
    assert all(decision.route == NO_SKILL_MATCH for decision in ranked)
    assert ranked[0].reasons == ("no_trigger_or_domain_match",)
    assert filtered == ()


def test_skill_routing_index_is_stable_and_body_free():
    index = build_skill_routing_index(
        [
            {
                "name": "task-forest",
                "trigger_terms": ["$task-forest"],
                "domains": ["task graph", "session history"],
                "validation_status": "tested",
            },
            {
                "name": "task-clarifier",
                "trigger_terms": ["$task-clarifier"],
                "domains": ["scope"],
                "validation_status": "documented",
            },
        ]
    )

    assert index == {
        "schema_version": 1,
        "skill_count": 2,
        "skills": [
            {
                "domains": ["scope"],
                "enabled": True,
                "name": "task-clarifier",
                "trigger_terms": ["$task-clarifier"],
                "validation_status": "documented",
            },
            {
                "domains": ["task graph", "session history"],
                "enabled": True,
                "name": "task-forest",
                "trigger_terms": ["$task-forest"],
                "validation_status": "tested",
            },
        ],
    }


def test_select_skill_returns_top_deterministic_match_with_ranked_context():
    skills = [
        SkillDescriptor(name="task-clarifier", trigger_terms=("$task-clarifier",), validation_status="tested"),
        SkillDescriptor(name="workflow-router", domains=("workflow",), validation_status="validated"),
    ]

    selection = select_skill_for_task("Use $task-clarifier before changing this workflow.", skills)

    assert selection.route == EXACT_TRIGGER_MATCH
    assert selection.selected is not None
    assert selection.selected.descriptor.name == "task-clarifier"
    assert [decision.descriptor.name for decision in selection.ranked] == ["task-clarifier", "workflow-router"]
    assert selection.diagnostics == ()


def test_select_skill_falls_back_when_no_skill_matches():
    skills = [
        SkillDescriptor(name="task-clarifier", trigger_terms=("$task-clarifier",), domains=("scope",)),
        SkillDescriptor(name="task-forest", trigger_terms=("$task-forest",), domains=("task graph",)),
    ]

    selection = select_skill_for_task("Summarize repository files.", skills)

    assert selection.route == NO_SKILL_MATCH
    assert selection.selected is None
    assert selection.ranked == ()
    assert selection.diagnostics == ("no_skills_matched",)


def test_select_skill_marks_tied_top_matches_as_ambiguous():
    skills = [
        SkillDescriptor(name="alpha-skill", trigger_terms=("$alpha-skill",), validation_status="tested"),
        SkillDescriptor(name="beta-skill", trigger_terms=("$beta-skill",), validation_status="tested"),
    ]

    selection = select_skill_for_task("Use $alpha-skill and $beta-skill to plan this task.", skills)

    assert selection.route == AMBIGUOUS_SKILL_MATCH
    assert selection.selected is None
    assert [decision.descriptor.name for decision in selection.ambiguous_candidates] == [
        "alpha-skill",
        "beta-skill",
    ]
    assert selection.diagnostics == ("ambiguous_top_skill_match:alpha-skill,beta-skill",)


def test_external_skill_route_discovery_fixture_stays_classification_only():
    fixture_path = Path(__file__).parent / "fixtures" / "skill_route_discovery" / "disabled_external_candidates.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry(payload["candidates"])

    assert registry["registry_status"] == "classification_only"
    assert registry["allowed_candidate_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert registry["allowed_source_hosts"] == ["github.com", "www.github.com"]
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert [candidate["name"] for candidate in registry["candidates"]] == [
        "codex-fable5",
        "compass-skills",
        "threejs-game-skills",
    ]
    assert {candidate["route_status"] for candidate in registry["candidates"]} == {SKILL_ROUTE_DISCOVERY_DISABLED}
    assert all(candidate["route_hints"] == ["skill_route_discovery"] for candidate in registry["candidates"])
    assert all(candidate["validation_errors"] == [] for candidate in registry["candidates"])
    assert all(candidate["discovery_event_effect"] == "record_only" for candidate in registry["candidates"])
    assert all(
        candidate["uncertainty"]
        == (
            "External skill evidence is unvalidated repository-level routing evidence; keep proposals local, "
            "bounded, and separately validated."
        )
        for candidate in registry["candidates"]
    )
    assert all(
        candidate["uncertainty_reasons"]
        == [
            "unvalidated_external_skill_evidence",
            "single_repository_level_source",
            "no_selected_digest_item_ids",
        ]
        for candidate in registry["candidates"]
    )


def test_external_skill_route_discovery_rejects_enabled_or_unbounded_candidates():
    registry = build_skill_route_discovery_registry(
        [
            ExternalSkillRouteCandidate(
                name="unsafe-enabled-skill",
                source_url="https://github.com/example/unsafe-enabled-skill",
                candidate_lanes=("documentation", "runtime_execution"),
                enabled=True,
            )
        ]
    )

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["enabled_candidate_count"] == 1
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 1
    assert registry["candidates"][0]["route_status"] == SKILL_ROUTE_DISCOVERY_INVALID
    assert registry["candidates"][0]["validation_errors"] == [
        "external_skill_route_candidates_must_start_disabled",
        "unsupported_candidate_lanes:runtime_execution",
    ]


def test_external_skill_route_discovery_rejects_non_public_or_decorated_source_urls():
    registry = build_skill_route_discovery_registry(
        [
            {
                "name": "local-skill",
                "source_url": "file:///tmp/local-skill",
            },
            {
                "name": "private-host-skill",
                "source_url": "https://git.internal.example/team/private-skill",
            },
            {
                "name": "github-owner-only",
                "source_url": "https://github.com/example",
            },
            {
                "name": "github-url-with-tokenish-query",
                "source_url": "https://github.com/example/public-skill?token=secret",
            },
        ]
    )

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 4
    assert [candidate["name"] for candidate in registry["candidates"]] == [
        "github-owner-only",
        "github-url-with-tokenish-query",
        "local-skill",
        "private-host-skill",
    ]
    assert [candidate["validation_errors"] for candidate in registry["candidates"]] == [
        ["source_url_must_include_repository_owner_and_name"],
        ["source_url_must_be_plain_repository_url"],
        ["source_url_must_use_https"],
        ["source_url_must_be_public_github_repository"],
    ]


def test_external_skill_route_discovery_lifecycle_events_cannot_install_execute_or_delete():
    fixture_path = Path(__file__).parent / "fixtures" / "skill_route_discovery" / "lifecycle_external_candidates.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry(payload["candidates"])

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 2
    assert registry["blocked_discovery_actions"] == [
        "clone_and_run",
        "delete_local_skill",
        "enable",
        "execute",
        "install",
        "run",
    ]

    created, deleted = registry["candidates"]
    assert created["name"] == "new-skill-package"
    assert created["discovery_event_kind"] == "repository_created"
    assert created["discovery_event_effect"] == "record_only_no_install"
    assert created["candidate_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert created["requested_actions"] == ["install"]
    assert created["validation_errors"] == [
        "unsupported_candidate_lanes:runtime_execution",
        "blocked_discovery_actions:install",
    ]

    assert deleted["name"] == "removed-skill-package"
    assert deleted["discovery_event_kind"] == "repository_deleted"
    assert deleted["discovery_event_effect"] == "record_only_no_local_deletion"
    assert deleted["candidate_lanes"] == ["documentation", "test"]
    assert deleted["requested_actions"] == ["delete_local_skill", "execute"]
    assert deleted["validation_errors"] == [
        "blocked_discovery_actions:delete_local_skill,execute",
    ]


def test_skill_route_discovery_classifies_summaries_into_bounded_lanes():
    fixture_path = Path(__file__).parent / "fixtures" / "skill_route_discovery" / "synthetic_repository_summaries.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_summaries(payload["summaries"])

    assert registry["registry_status"] == "classification_only"
    assert registry["summary_count"] == 4
    assert registry["ignored_summary_count"] == 1
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert [candidate["name"] for candidate in registry["candidates"]] == [
        "codex-fable5",
        "compass-skills",
        "threejs-game-skills",
    ]

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    for candidate in registry["candidates"]:
        assert set(candidate["candidate_lanes"]) <= allowed_lanes
        assert candidate["route_status"] == SKILL_ROUTE_DISCOVERY_DISABLED
        assert candidate["requested_actions"] == []
        assert candidate["validation_errors"] == []
        assert candidate["enabled"] is False

    lanes_by_name = {candidate["name"]: candidate["candidate_lanes"] for candidate in registry["candidates"]}
    assert lanes_by_name["codex-fable5"] == ["documentation", "test", "config", "code_patch"]
    assert lanes_by_name["compass-skills"] == ["config", "test", "documentation", "code_patch"]
    assert lanes_by_name["threejs-game-skills"] == ["documentation", "code_patch", "test"]
    profiles_by_name = {candidate["name"]: candidate["route_profiles"] for candidate in registry["candidates"]}
    assert profiles_by_name["codex-fable5"] == ["codex_workflow_gate"]
    assert profiles_by_name["compass-skills"] == ["skill_ecosystem_state_handoff"]
    assert profiles_by_name["threejs-game-skills"] == ["game_frontend_workflow"]


def test_skill_route_discovery_summary_classifier_defaults_to_documentation_only():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            ExternalSkillRepositorySummary(
                name="minimal-skill-note",
                source_url="https://github.com/example/minimal-skill-note",
                summary="Tiny agent skill note with naming signal only.",
            )
        ]
    )

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 1
    assert registry["candidates"][0]["candidate_lanes"] == ["documentation"]
    assert registry["candidates"][0]["requested_actions"] == []


def test_skill_route_discovery_classifies_body_free_file_layout_into_local_lanes():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "summary": "Directory snapshot with task clarification, profile state, validation checks, and prompts.",
                "observed_paths": [
                    "skills/task-clarifier/SKILL.md",
                    "skills/local-memory/SKILL.md",
                    "scripts/validate_skill_metadata.py",
                    "prompts/handoff.md",
                    "PUBLICATION_AUDIT.md",
                ],
                "metadata_files": ["skills.sh.json", "AGENTS.md"],
            },
            {
                "name": "FableCodex",
                "source_url": "https://github.com/baskduf/FableCodex",
                "summary": "Codex workflow skill package with plugin route gate and local verification.",
                "observed_paths": [
                    ".codex-plugin/plugin.json",
                    "tests/test_workflow_gate.py",
                    "examples/replay-template.md",
                ],
                "suggested_lanes": ["agent_harness_eval", "install"],
            },
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "summary": "Browser game workflow directory snapshot with Three.js QA and scaffold boundaries.",
                "observed_paths": [
                    "skills/game-director/SKILL.md",
                    "qa/browser-canvas-checklist.md",
                    "scaffold/vite-threejs-game/template.ts",
                ],
            },
            {
                "name": "generic-agent-docs",
                "source_url": "https://github.com/example/generic-agent-docs",
                "summary": "Generic repository instructions without reusable skill package evidence.",
                "observed_paths": ["AGENTS.md"],
            },
        ]
    )
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["summary_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["ignored_summary_count"] == 1

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    assert set(candidates_by_name["compass-skills"]["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert candidates_by_name["compass-skills"]["source_layout_signals"] == [
        "skill_markdown",
        "skill_directory",
        "validation_script",
        "template_or_prompt",
    ]
    assert candidates_by_name["compass-skills"]["source_metadata_signals"] == [
        "skill_registry_metadata",
        "agent_metadata",
        "qa_checklist",
    ]
    assert set(candidates_by_name["FableCodex"]["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert candidates_by_name["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]

    inventory_by_name = {row["candidate_name"]: row for row in lane_map["candidate_lane_inventory"]}
    assert inventory_by_name["compass-skills"]["source_layout_signals"] == [
        "skill_markdown",
        "skill_directory",
        "validation_script",
        "template_or_prompt",
    ]
    assert inventory_by_name["compass-skills"]["source_metadata_signals"] == [
        "skill_registry_metadata",
        "agent_metadata",
        "qa_checklist",
    ]
    assert inventory_by_name["compass-skills"]["runtime_action"] == "none"
    assert inventory_by_name["compass-skills"]["external_skill_activation_allowed"] is False
    assert inventory_by_name["FableCodex"]["route_probe_decision"] == "skill_route_discovery_first"
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
        if lane["candidate_name"] == "FableCodex"
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)


def test_skill_route_discovery_summary_classifier_collapses_fork_lineage():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "summary": "Director skill package with specialist Three.js game workflow skills and QA helpers.",
                "suggested_lanes": ["documentation", "test", "code_patch"],
            },
            {
                "name": "threejs-game-skills-fork",
                "source_url": "https://github.com/pretinhuu1-boop/threejs-game-skills",
                "upstream_source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "summary": "Fork of the same director skill package with workflow skills, routing config, and validation helpers.",
                "suggested_lanes": ["documentation", "config", "test", "code_patch"],
            },
        ]
    )

    assert registry["registry_status"] == "classification_only"
    assert registry["summary_count"] == 2
    assert registry["candidate_count"] == 1
    assert registry["duplicate_summary_count"] == 1
    assert registry["ignored_summary_count"] == 0

    candidate = registry["candidates"][0]
    assert candidate["name"] == "threejs-game-skills"
    assert candidate["source_url"] == "https://github.com/majidmanzarpour/threejs-game-skills"
    assert candidate["candidate_lanes"] == ["documentation", "test", "code_patch", "config"]
    assert candidate["related_source_urls"] == [
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "https://github.com/pretinhuu1-boop/threejs-game-skills",
    ]
    assert candidate["route_status"] == SKILL_ROUTE_DISCOVERY_DISABLED
    assert candidate["validation_errors"] == []


def test_skill_route_discovery_current_window_game_frontend_evidence_stays_bounded():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_game_frontend_lanes.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_summaries(payload["summaries"])
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["summary_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["duplicate_summary_count"] == 1
    assert registry["ignored_summary_count"] == 0
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    assert candidates_by_name["threejs-game-skills"]["related_source_urls"] == [
        "https://github.com/majidmanzarpour/threejs-game-skills",
        "https://github.com/LeanEntropy/threejs-phaser-game-skills",
    ]
    assert candidates_by_name["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert candidates_by_name["threejs-game-skills"]["candidate_lanes"] == [
        "documentation",
        "test",
        "code_patch",
        "config",
    ]

    assert lane_map["source_registry_status"] == "classification_only"
    assert lane_map["candidate_count"] == 3
    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(row["runtime_action"] == "none" for row in lane_map["candidate_lane_inventory"])
    assert all(row["external_skill_activation_allowed"] is False for row in lane_map["candidate_lane_inventory"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])

    game_inventory = next(
        row for row in lane_map["candidate_lane_inventory"] if row["candidate_name"] == "threejs-game-skills"
    )
    assert game_inventory["route_profiles"] == ["game_frontend_workflow"]
    assert game_inventory["proposal_kinds"] == ["documentation", "test", "code_patch", "config"]
    assert game_inventory["route_validation_contract"]["rows"][0]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert game_inventory["route_validation_contract"]["rows"][0]["preferred_local_lanes"] == [
        "test",
        "documentation",
        "code_patch",
        "config",
    ]
    assert game_inventory["route_validation_contract"]["runtime_action"] == "none"
    assert game_inventory["route_validation_contract"]["external_skill_activation_allowed"] is False
    assert game_inventory["route_validation_contract"]["provider_launch_allowed"] is False
    assert game_inventory["route_validation_contract"]["remote_execution_allowed"] is False


def test_skill_route_discovery_provider_runtime_pass2_four_item_matrix_requires_local_validation():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "provider_runtime_pass2_four_item_evidence.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 4
    assert registry["candidate_count"] == 4
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert lane_map["proposal_lane_count"] == 16
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    assert {
        name: candidate["route_profiles"]
        for name, candidate in candidates_by_name.items()
    } == {
        "FableCodex": ["codex_workflow_gate"],
        "compass-skills": ["skill_ecosystem_state_handoff"],
        "threejs-game-skills": ["game_frontend_workflow"],
        "zhengxi-views": ["source_cited_domain_research"],
    }
    for candidate in registry["candidates"]:
        assert set(candidate["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert candidate["route_hints"] == ["skill_route_discovery"]
        assert candidate["validation_errors"] == []
        assert candidate["requested_actions"] == []
        assert candidate["enabled"] is False

    inventory_by_name = {row["candidate_name"]: row for row in lane_map["candidate_lane_inventory"]}
    assert set(inventory_by_name) == {
        "FableCodex",
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    }
    for row in lane_map["candidate_lane_inventory"]:
        assert set(row["proposal_kinds"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["activation_gate"] == "local_validation_before_activation"
        assert row["route_validation_contract"]["local_validation_required"] is True
        assert row["route_validation_contract"]["provider_launch_allowed"] is False
        assert row["handoff_metadata"]["provider_runtime_launch_allowed"] is False
        assert row["handoff_metadata"]["external_harness_execution_allowed"] is False
        assert row["handoff_metadata"]["remote_execution_allowed"] is False
        assert row["handoff_metadata"]["raw_evidence_urls_exported"] is False
        assert row["handoff_metadata"]["raw_upstream_body_exported"] is False

    fablecodex = inventory_by_name["FableCodex"]
    assert fablecodex["route_probe_decision"] == "skill_route_discovery_first"
    assert fablecodex["primary_route"] == "skill_route_discovery"
    assert fablecodex["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert fablecodex["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert fablecodex["agent_harness_eval_allowed_after"] == (
        "local_corroboration_or_general_agent_project_claim"
    )

    lane_matrix = lane_map["local_lane_matrix"]
    assert lane_matrix["status"] == "ready"
    assert lane_matrix["row_count"] == 4
    assert set(lane_matrix["observed_route_profiles"]) == {
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    }
    assert set(lane_matrix["observed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane_matrix["local_validation_required"] is True
    assert lane_matrix["runtime_action"] == "none"
    assert lane_matrix["external_skill_activation_allowed"] is False
    assert lane_matrix["external_harness_execution_allowed"] is False
    assert lane_matrix["provider_runtime_launch_allowed"] is False
    assert lane_matrix["remote_execution_allowed"] is False
    assert lane_matrix["raw_source_url_exported"] is False
    assert lane_matrix["raw_upstream_body_exported"] is False

    matrix_rows = {row["candidate_name"]: row for row in lane_matrix["rows"]}
    assert matrix_rows["FableCodex"]["selected_local_lane"] == "test"
    assert matrix_rows["FableCodex"]["route_probe_decision"] == "skill_route_discovery_first"
    assert matrix_rows["FableCodex"]["first_route_required"] is True
    assert matrix_rows["compass-skills"]["selected_local_lane"] == "config"
    assert matrix_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert matrix_rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert matrix_rows["zhengxi-views"]["validation_gates"] == [
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    ]

    next_step = lane_map["next_validation_step"]
    assert next_step["status"] == "ready"
    assert next_step["selected_candidate_name"] == "FableCodex"
    assert next_step["selected_local_lane"] == "test"
    assert next_step["validation_target"] == "skill_route_first_probe_regression"
    assert next_step["promotion_proof"]["required_evidence"] == [
        "changed_file_review",
        "focused_local_validation",
        "rollback_artifact",
        "review_note",
    ]
    assert next_step["promotion_proof"]["provider_runtime_launch_allowed"] is False
    assert next_step["provider_runtime_launch_allowed"] is False
    assert next_step["external_harness_execution_allowed"] is False
    assert next_step["remote_execution_allowed"] is False
    assert next_step["raw_evidence_urls_exported"] is False
    assert next_step["raw_upstream_body_exported"] is False

    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["external_skill_activation_allowed"] is False for lane in lane_map["proposal_lanes"])
    assert all(lane["provider_runtime_launch_allowed"] is False for lane in lane_map["proposal_lanes"])
    assert all(
        set(lane["evidence_item_ids"]) <= {item["item_id"] for item in payload["items"]}
        for lane in lane_map["proposal_lanes"]
    )


def test_skill_route_discovery_classifies_issue_evidence_without_duplicate_candidates():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "fablecodex_issue_evidence_items.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 5
    assert registry["ignored_evidence_item_count"] == 1
    assert registry["duplicate_evidence_item_count"] == 1
    assert registry["candidate_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    candidate = registry["candidates"][0]
    assert candidate["name"] == "codex-fable5"
    assert candidate["source_url"] == "https://github.com/baskduf/FableCodex"
    assert candidate["route_status"] == SKILL_ROUTE_DISCOVERY_DISABLED
    assert candidate["evidence_urls"] == [
        "https://github.com/baskduf/FableCodex",
        "https://github.com/baskduf/FableCodex/issues/15",
        "https://github.com/baskduf/FableCodex/issues/18",
    ]
    assert candidate["evidence_item_urls"] == [
        "https://github.com/baskduf/FableCodex",
        "https://github.com/baskduf/FableCodex/issues/15",
        "https://github.com/baskduf/FableCodex/issues/18",
    ]
    assert candidate["evidence_item_ids"] == [
        "fablecodex-repo",
        "fablecodex-issue-15",
        "fablecodex-issue-15-repeat",
        "fablecodex-issue-18",
    ]
    assert candidate["candidate_lanes"] == ["documentation", "test", "config", "code_patch"]
    assert candidate["route_profiles"] == ["codex_workflow_gate"]
    assert set(candidate["candidate_lanes"]) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert candidate["requested_actions"] == []
    assert candidate["validation_errors"] == []
    assert candidate["enabled"] is False


def test_skill_route_discovery_issue_evidence_requires_explicit_hint():
    registry = build_skill_route_discovery_registry_from_evidence_items(
        [
            ExternalSkillEvidenceItem(
                item_kind="issue",
                source_url="https://github.com/baskduf/FableCodex/issues/18",
                title="Add user-facing FableCodex workflow examples",
                summary="Codex skill workflow examples with docs and tests.",
                route_hints=("general_trend",),
                suggested_lanes=("documentation", "test"),
            )
        ]
    )

    assert registry["candidate_count"] == 0
    assert registry["ignored_evidence_item_count"] == 1


def test_skill_route_discovery_proposal_lane_map_bounds_recognized_skill_evidence():
    fixture_path = Path(__file__).parent / "fixtures" / "skill_route_discovery" / "synthetic_repository_summaries.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_summaries(payload["summaries"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["source_registry_status"] == "classification_only"
    assert lane_map["candidate_count"] == 3
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0
    assert lane_map["allowed_proposal_kinds"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane_map["proposal_lane_count"] == 11
    assert [row["candidate_name"] for row in lane_map["candidate_lane_inventory"]] == [
        "codex-fable5",
        "compass-skills",
        "threejs-game-skills",
    ]
    assert {
        lane
        for row in lane_map["candidate_lane_inventory"]
        for lane in row["proposal_kinds"]
    } <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(row["runtime_action"] == "none" for row in lane_map["candidate_lane_inventory"])
    assert all(row["local_validation_required"] is True for row in lane_map["candidate_lane_inventory"])
    assert all(
        row["external_skill_activation_allowed"] is False
        for row in lane_map["candidate_lane_inventory"]
    )
    assert all(
        row["activation_gate"] == "local_validation_before_activation"
        for row in lane_map["candidate_lane_inventory"]
    )
    compass_inventory = next(
        row for row in lane_map["candidate_lane_inventory"] if row["candidate_name"] == "compass-skills"
    )
    compass_handoff = compass_inventory["handoff_metadata"]
    assert compass_handoff["controller_surface"] == "skill_route_discovery_lane_handoff_metadata"
    assert compass_handoff["handoff_scope"] == "candidate_inventory"
    assert compass_handoff["status"] == "ready"
    assert compass_handoff["allowed_local_lanes"] == ["config", "test", "documentation", "code_patch"]
    assert compass_handoff["selected_local_lane"] == "config"
    assert compass_handoff["queued_local_lanes"] == ["test", "documentation", "code_patch"]
    assert compass_handoff["validation_gates"] == ["state_handoff_boundary_before_profile_or_memory_write"]
    assert compass_handoff["local_validation_required"] is True
    assert compass_handoff["runtime_action"] == "none"
    assert compass_handoff["external_skill_activation_allowed"] is False
    assert compass_handoff["external_harness_execution_allowed"] is False
    assert compass_handoff["provider_runtime_launch_allowed"] is False
    assert compass_handoff["remote_execution_allowed"] is False
    assert compass_handoff["raw_source_url_exported"] is False
    assert compass_handoff["raw_evidence_urls_exported"] is False
    assert compass_handoff["raw_upstream_body_exported"] is False
    compass_contract = compass_inventory["route_validation_contract"]
    assert compass_contract["controller_surface"] == "skill_route_discovery_route_validation_contract"
    assert compass_contract["status"] == "ready"
    assert compass_contract["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert compass_contract["allowed_local_lanes"] == ["config", "test", "documentation", "code_patch"]
    assert compass_contract["rows"][0]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert compass_contract["rows"][0]["preferred_local_lanes"] == [
        "config",
        "test",
        "documentation",
        "code_patch",
    ]
    fablecodex_lanes = [
        lane for lane in lane_map["proposal_lanes"] if lane["candidate_name"] == "codex-fable5"
    ]
    assert {
        lane["route_validation_contract"]["rows"][0]["validation_gate"]
        for lane in fablecodex_lanes
    } == {"skill_route_discovery_first_before_workflow_gate"}
    assert all(
        lane["route_validation_contract"]["allowed_local_lanes"] == [lane["proposal_kind"]]
        for lane in fablecodex_lanes
    )
    assert all(
        lane["handoff_metadata"]["handoff_scope"] == "proposal_lane"
        and lane["handoff_metadata"]["selected_local_lane"] == lane["proposal_kind"]
        and lane["handoff_metadata"]["queued_local_lanes"] == []
        and lane["handoff_metadata"]["runtime_action"] == "none"
        and lane["handoff_metadata"]["external_skill_activation_allowed"] is False
        for lane in fablecodex_lanes
    )
    threejs_inventory = next(
        row for row in lane_map["candidate_lane_inventory"] if row["candidate_name"] == "threejs-game-skills"
    )
    assert threejs_inventory["route_validation_contract"]["rows"][0]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert threejs_inventory["route_validation_contract"]["rows"][0]["preferred_local_lanes"] == [
        "test",
        "documentation",
        "code_patch",
    ]
    assert compass_inventory["state_profile_boundary"] == {
        "boundary_required_before_activation": True,
        "retention_policy_required": True,
        "privacy_boundary_required": True,
        "local_target_metadata_only": True,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "global_config_write_allowed": False,
        "private_context_export_allowed": False,
        "upstream_presence_grants_write": False,
        "review_surface": "skill_route_discovery_state_handoff_preflight",
    }
    assert all(
        "state_profile_boundary" not in row
        for row in lane_map["candidate_lane_inventory"]
        if row["candidate_name"] != "compass-skills"
    )
    assert lane_map["local_lane_matrix"]["controller_surface"] == "skill_route_discovery_local_lane_matrix"
    assert lane_map["local_lane_matrix"]["status"] == "ready"
    assert lane_map["local_lane_matrix"]["row_count"] == 3
    assert lane_map["local_lane_matrix"]["observed_route_profiles"] == [
        "codex_workflow_gate",
        "skill_ecosystem_state_handoff",
        "game_frontend_workflow",
    ]
    assert lane_map["local_lane_matrix"]["observed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane_map["local_lane_matrix"]["runtime_action"] == "none"
    assert lane_map["local_lane_matrix"]["external_skill_activation_allowed"] is False
    assert lane_map["local_lane_matrix"]["external_harness_execution_allowed"] is False
    assert lane_map["local_lane_matrix"]["provider_runtime_launch_allowed"] is False
    assert lane_map["local_lane_matrix"]["remote_execution_allowed"] is False
    assert lane_map["local_lane_matrix"]["raw_source_url_exported"] is False
    assert lane_map["local_lane_matrix"]["raw_upstream_body_exported"] is False
    matrix_rows = {row["candidate_name"]: row for row in lane_map["local_lane_matrix"]["rows"]}
    assert matrix_rows["codex-fable5"]["selected_local_lane"] == "test"
    assert matrix_rows["codex-fable5"]["queued_local_lanes"] == ["documentation", "config", "code_patch"]
    assert matrix_rows["codex-fable5"]["route_probe_decision"] == "skill_route_discovery_first"
    assert matrix_rows["codex-fable5"]["first_route_required"] is True
    assert matrix_rows["codex-fable5"]["first_route_confirmed"] is True
    assert matrix_rows["compass-skills"]["selected_local_lane"] == "config"
    assert matrix_rows["compass-skills"]["first_route_required"] is False
    assert matrix_rows["threejs-game-skills"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert lane_map["route_profile_catalog"] == {
        "body_free": True,
        "profile_counts": {
            "codex_workflow_gate": 4,
            "game_frontend_workflow": 3,
            "skill_ecosystem_state_handoff": 4,
        },
        "profile_lane_counts": {
            "codex_workflow_gate:code_patch": 1,
            "codex_workflow_gate:config": 1,
            "codex_workflow_gate:documentation": 1,
            "codex_workflow_gate:test": 1,
            "game_frontend_workflow:code_patch": 1,
            "game_frontend_workflow:documentation": 1,
            "game_frontend_workflow:test": 1,
            "skill_ecosystem_state_handoff:code_patch": 1,
            "skill_ecosystem_state_handoff:config": 1,
            "skill_ecosystem_state_handoff:documentation": 1,
            "skill_ecosystem_state_handoff:test": 1,
        },
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }
    adoption_manifest = lane_map["adoption_manifest"]
    assert adoption_manifest["controller_surface"] == "skill_route_discovery_adoption_manifest"
    assert adoption_manifest["status"] == "ready"
    assert adoption_manifest["decision"] == "bounded_local_validation_only"
    assert adoption_manifest["candidate_count"] == 3
    assert adoption_manifest["proposal_lane_count"] == 11
    assert adoption_manifest["observed_route_profiles"] == [
        "codex_workflow_gate",
        "skill_ecosystem_state_handoff",
        "game_frontend_workflow",
    ]
    assert adoption_manifest["observed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert adoption_manifest["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert adoption_manifest["activation_gate"] == "local_validation_before_activation"
    assert adoption_manifest["local_validation_required"] is True
    assert adoption_manifest["runtime_action"] == "none"
    assert adoption_manifest["external_skill_activation_allowed"] is False
    assert adoption_manifest["external_harness_execution_allowed"] is False
    assert adoption_manifest["provider_runtime_launch_allowed"] is False
    assert adoption_manifest["remote_execution_allowed"] is False
    assert adoption_manifest["raw_source_url_exported"] is False
    assert adoption_manifest["raw_evidence_urls_exported"] is False
    assert adoption_manifest["raw_target_paths_exported"] is False
    assert adoption_manifest["raw_upstream_body_exported"] is False
    assert adoption_manifest["promotion_readiness"] == {
        "controller_surface": "skill_route_discovery_promotion_readiness",
        "status": "ready",
        "decision": "replay_bounded_lanes_then_external_supervisor_handoff",
        "row_count": 3,
        "ready_row_count": 3,
        "blocked_row_count": 0,
        "selected_local_lanes": ["config", "test"],
        "replay_commands": [
            "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow",
            "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
            "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
        ],
        "required_evidence": [
            "rollback_ref",
            "rollback_artifact",
            "changed_file_review",
            "focused_local_validation",
            "review_note",
        ],
        "target_path_hashes": [
            "sha256:9a38f861c194d9e5e004d0f4837e81c564d6cacca53d5f62e09fe0952684650d",
            "sha256:35e8cf2fc42afff1abd6f9335f74413eac5addc1a1495417739324e0ae26a044",
            "sha256:a162fbd0b395a34769d0b6de13b75f37e568c0eb3f0e54e51aad4f6bce17007d",
        ],
        "target_path_count": 3,
        "supervisor_handoff": "external_supervisor_only",
        "kernel_restart_allowed": False,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert {
        "install",
        "execute",
        "activate_upstream_skill_code",
        "provider_runtime_launch",
        "remote_execution",
        "raw_source_url_export",
        "raw_upstream_body_export",
    } <= set(adoption_manifest["blocked_external_actions"])
    manifest_rows = {row["candidate_name"]: row for row in adoption_manifest["rows"]}
    assert manifest_rows["codex-fable5"]["selected_local_lane"] == "test"
    assert manifest_rows["codex-fable5"]["first_route_confirmed"] is True
    assert manifest_rows["codex-fable5"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow"
    )
    assert manifest_rows["codex-fable5"]["promotion_proof"]["selected_local_lane"] == "test"
    assert manifest_rows["compass-skills"]["selected_local_lane"] == "config"
    assert manifest_rows["compass-skills"]["validation_target"] == "state_or_profile_boundary_metadata"
    assert manifest_rows["compass-skills"]["promotion_proof"]["selected_local_lane"] == "config"
    assert manifest_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert manifest_rows["threejs-game-skills"]["validation_target"] == "local_frontend_render_or_workflow_check"
    assert manifest_rows["threejs-game-skills"]["promotion_proof"]["selected_local_lane"] == "test"
    assert all(row["manifest_status"] == "ready_for_local_validation" for row in adoption_manifest["rows"])
    assert all(row["runtime_action"] == "none" for row in adoption_manifest["rows"])
    assert all(row["local_validation_required"] is True for row in adoption_manifest["rows"])
    assert all("source_url" not in row for row in adoption_manifest["rows"])
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_hint"] == "skill_route_discovery" for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["route_profiles"] for lane in lane_map["proposal_lanes"])
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])
    assert all(lane["uncertainty"] for lane in lane_map["proposal_lanes"])
    assert all("unvalidated_external_skill_evidence" in lane["uncertainty_reasons"] for lane in lane_map["proposal_lanes"])
    compass_lanes = [
        lane for lane in lane_map["proposal_lanes"] if lane["candidate_name"] == "compass-skills"
    ]
    assert {lane["proposal_kind"] for lane in compass_lanes} == {"documentation", "config", "test", "code_patch"}
    assert all(
        lane["state_profile_boundary"]["profile_write_allowed"] is False
        and lane["state_profile_boundary"]["memory_write_allowed"] is False
        and lane["state_profile_boundary"]["private_context_export_allowed"] is False
        for lane in compass_lanes
    )
    assert all(
        "state_profile_boundary" not in lane
        for lane in lane_map["proposal_lanes"]
        if lane["candidate_name"] != "compass-skills"
    )


def test_skill_route_discovery_normalizes_push_event_to_bounded_proposal_lanes():
    registry = build_skill_route_discovery_registry_from_evidence_items(
        [
            {
                "item_id": "compass-push",
                "item_kind": "repository",
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "title": "COMPASS Skills PushEvent",
                "summary": (
                    "PushEvent movement for a skill ecosystem with task clarification, local memory, "
                    "handoff prompts, profile state, route metadata, and validation notes."
                ),
                "discovery_event_kind": "PushEvent",
                "route_hints": ["skill_route_discovery"],
                "topics": ["agent-skills", "workflow", "validation"],
                "suggested_lanes": ["documentation", "config", "test", "code_patch", "install"],
            }
        ]
    )
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["candidate_count"] == 1
    assert registry["candidates"][0]["discovery_event_kind"] == "push"
    assert registry["candidates"][0]["discovery_event_effect"] == "record_only"
    assert lane_map["proposal_lane_count"] == 4
    assert {lane["proposal_kind"] for lane in lane_map["proposal_lanes"]} == {
        "documentation",
        "config",
        "test",
        "code_patch",
    }
    assert {lane["discovery_event_kind"] for lane in lane_map["proposal_lanes"]} == {"push"}
    assert {lane["runtime_action"] for lane in lane_map["proposal_lanes"]} == {"none"}
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_source_cited_domain_research_stays_bounded_and_non_advisory():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "zhengxi-views",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "summary": (
                    "Agent Skill for traceable public investment research views, source-cited QA, "
                    "fund scoring examples, advice disclaimers, and local validation notes."
                ),
                "topics": ["agent-skill", "research", "source-cited", "investment", "validation"],
                "suggested_lanes": ["documentation", "config", "test", "code_patch", "provider_launch"],
                "observed_paths": [
                    "skills/zhengxi-views/SKILL.md",
                    "docs/source-citations.md",
                    "tests/test_citation_boundaries.py",
                ],
            }
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 1
    candidate = registry["candidates"][0]
    assert candidate["name"] == "zhengxi-views"
    assert candidate["candidate_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert candidate["route_profiles"] == ["source_cited_domain_research"]

    inventory = lane_map["candidate_lane_inventory"][0]
    assert inventory["proposal_kinds"] == ["documentation", "config", "test", "code_patch"]
    assert inventory["route_profiles"] == ["source_cited_domain_research"]
    assert inventory["handoff_metadata"]["selected_local_lane"] == "test"
    assert inventory["handoff_metadata"]["queued_local_lanes"] == ["documentation", "config", "code_patch"]
    assert inventory["handoff_metadata"]["validation_gates"] == [
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    ]
    assert inventory["domain_research_boundary"] == {
        "boundary_required_before_activation": True,
        "source_citation_required": True,
        "advice_disclaimer_required": True,
        "local_evidence_replay_required": True,
        "upstream_dataset_import_allowed": False,
        "upstream_advice_generation_allowed": False,
        "financial_or_medical_advice_allowed": False,
        "provider_runtime_launch_allowed": False,
        "private_context_export_allowed": False,
        "review_surface": "skill_route_discovery_domain_research_preflight",
    }

    activation_target = lane_map["local_activation_targets"]["rows"][0]
    assert activation_target["candidate_name"] == "zhengxi-views"
    assert activation_target["selected_local_lane"] == "test"
    assert activation_target["validation_target"] == "source_citation_and_advice_boundary_check"
    assert activation_target["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k source_cited_domain_research"
    )
    assert activation_target["runtime_action"] == "none"
    assert activation_target["external_skill_activation_allowed"] is False
    assert activation_target["provider_runtime_launch_allowed"] is False
    assert activation_target["raw_source_url_exported"] is False
    assert activation_target["raw_upstream_body_exported"] is False

    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_hint"] == "skill_route_discovery" for lane in lane_map["proposal_lanes"])
    assert all(lane["domain_research_boundary"]["financial_or_medical_advice_allowed"] is False for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["external_skill_activation_allowed"] is False for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_current_window_matrix_keeps_profile_lanes_bounded():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_game_frontend_lanes.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_summaries(payload["summaries"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    matrix = lane_map["local_lane_matrix"]
    assert registry["candidate_count"] == 3
    assert matrix["status"] == "ready"
    assert matrix["row_count"] == 3
    assert matrix["observed_route_profiles"] == [
        "codex_workflow_gate",
        "skill_ecosystem_state_handoff",
        "game_frontend_workflow",
    ]
    assert set(matrix["observed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert matrix["blocked_candidate_names"] == []
    assert matrix["runtime_action"] == "none"
    assert matrix["external_skill_activation_allowed"] is False
    assert matrix["external_harness_execution_allowed"] is False
    assert matrix["provider_runtime_launch_allowed"] is False
    assert matrix["remote_execution_allowed"] is False
    assert matrix["raw_source_url_exported"] is False
    assert matrix["raw_upstream_body_exported"] is False

    activation_targets = lane_map["local_activation_targets"]
    assert activation_targets["controller_surface"] == "skill_route_discovery_local_activation_targets"
    assert activation_targets["status"] == "ready"
    assert activation_targets["row_count"] == 3
    assert activation_targets["blocked_candidate_names"] == []
    assert activation_targets["runtime_action"] == "none"
    assert activation_targets["external_skill_activation_allowed"] is False
    assert activation_targets["external_harness_execution_allowed"] is False
    assert activation_targets["provider_runtime_launch_allowed"] is False
    assert activation_targets["remote_execution_allowed"] is False
    assert activation_targets["raw_source_url_exported"] is False
    assert activation_targets["raw_evidence_urls_exported"] is False
    assert activation_targets["raw_upstream_body_exported"] is False

    profile_queue = lane_map["route_profile_handoff_queue"]
    assert profile_queue["controller_surface"] == "skill_route_discovery_route_profile_handoff_queue"
    assert profile_queue["status"] == "ready"
    assert profile_queue["decision"] == "handoff_route_profiles_to_bounded_local_validation"
    assert profile_queue["route_profile_count"] == 3
    assert profile_queue["blocked_route_profiles"] == []
    assert profile_queue["local_validation_required"] is True
    assert profile_queue["runtime_action"] == "none"
    assert profile_queue["external_skill_activation_allowed"] is False
    assert profile_queue["external_harness_execution_allowed"] is False
    assert profile_queue["provider_runtime_launch_allowed"] is False
    assert profile_queue["remote_execution_allowed"] is False
    assert profile_queue["raw_source_url_exported"] is False
    assert profile_queue["raw_evidence_urls_exported"] is False
    assert profile_queue["raw_target_paths_exported"] is False
    assert profile_queue["raw_upstream_body_exported"] is False
    profile_rows = {row["route_profile"]: row for row in profile_queue["rows"]}
    assert profile_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert profile_rows["codex_workflow_gate"]["validation_target"] == "skill_route_first_probe_regression"
    assert profile_rows["codex_workflow_gate"]["validation_gates"] == [
        "skill_route_discovery_first_before_workflow_gate"
    ]
    assert profile_rows["codex_workflow_gate"]["first_route_required"] is True
    assert profile_rows["codex_workflow_gate"]["first_route_confirmed"] is True
    assert profile_rows["codex_workflow_gate"]["queue_status"] == "ready"
    assert profile_rows["codex_workflow_gate"]["candidate_names"] == ["codex-fable5"]
    assert profile_rows["codex_workflow_gate"]["candidate_source_hashes"] == [
        "sha256:c27eb597f279b04dc64fe485a7756cce5edfebd1cee8cd68a1b8becb46c219cd"
    ]
    assert profile_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert profile_rows["skill_ecosystem_state_handoff"]["validation_target"] == "state_or_profile_boundary_metadata"
    assert profile_rows["skill_ecosystem_state_handoff"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert profile_rows["skill_ecosystem_state_handoff"]["first_route_required"] is False
    assert profile_rows["skill_ecosystem_state_handoff"]["queue_status"] == "ready"
    assert profile_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert profile_rows["game_frontend_workflow"]["validation_target"] == "local_frontend_render_or_workflow_check"
    assert profile_rows["game_frontend_workflow"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert all(row["runtime_action"] == "none" for row in profile_queue["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in profile_queue["rows"])
    assert all(row["raw_source_url_exported"] is False for row in profile_queue["rows"])
    assert all(row["raw_upstream_body_exported"] is False for row in profile_queue["rows"])

    pass1_matrix = lane_map["pass1_validation_matrix"]
    assert pass1_matrix["controller_surface"] == "skill_route_discovery_pass1_validation_matrix"
    assert pass1_matrix["status"] == "ready"
    assert pass1_matrix["decision"] == "replay_pass1_bounded_lanes_before_activation"
    assert pass1_matrix["row_count"] == 3
    assert pass1_matrix["ready_row_count"] == 3
    assert pass1_matrix["blocked_row_count"] == 0
    assert pass1_matrix["blocked_candidate_names"] == []
    assert pass1_matrix["selected_local_lanes"] == ["config", "test"]
    assert pass1_matrix["queued_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert pass1_matrix["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow",
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
    ]
    assert pass1_matrix["required_evidence"] == [
        "rollback_artifact",
        "focused_local_validation",
        "changed_file_review",
        "review_note",
    ]
    assert pass1_matrix["local_validation_required"] is True
    assert pass1_matrix["runtime_action"] == "none"
    assert pass1_matrix["external_skill_activation_allowed"] is False
    assert pass1_matrix["external_harness_execution_allowed"] is False
    assert pass1_matrix["provider_runtime_launch_allowed"] is False
    assert pass1_matrix["remote_execution_allowed"] is False
    assert pass1_matrix["raw_source_url_exported"] is False
    assert pass1_matrix["raw_evidence_urls_exported"] is False
    assert pass1_matrix["raw_target_paths_exported"] is False
    assert pass1_matrix["raw_upstream_body_exported"] is False
    pass1_rows = {row["candidate_name"]: row for row in pass1_matrix["rows"]}
    assert pass1_rows["codex-fable5"]["selected_local_lane"] == "test"
    assert pass1_rows["codex-fable5"]["queued_local_lanes"] == ["documentation", "config", "code_patch"]
    assert pass1_rows["codex-fable5"]["promotion_proof"]["selected_local_lane"] == "test"
    assert pass1_rows["codex-fable5"]["promotion_proof"]["raw_target_paths_exported"] is False
    assert pass1_rows["codex-fable5"]["first_route_required"] is True
    assert pass1_rows["codex-fable5"]["first_route_confirmed"] is True
    assert pass1_rows["codex-fable5"]["activation_ready"] is True
    assert pass1_rows["compass-skills"]["selected_local_lane"] == "config"
    assert pass1_rows["compass-skills"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff"
    )
    assert pass1_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert pass1_rows["threejs-game-skills"]["validation_target"] == "local_frontend_render_or_workflow_check"
    assert all(row["runtime_action"] == "none" for row in pass1_matrix["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in pass1_matrix["rows"])
    assert all(row["raw_source_url_exported"] is False for row in pass1_matrix["rows"])
    assert all(row["raw_target_paths_exported"] is False for row in pass1_matrix["rows"])
    assert all(row["raw_upstream_body_exported"] is False for row in pass1_matrix["rows"])

    next_step = lane_map["next_validation_step"]
    assert next_step["controller_surface"] == "skill_route_discovery_next_validation_step"
    assert next_step["status"] == "ready"
    assert next_step["decision"] == "run_selected_local_validation_before_activation"
    assert next_step["selected_candidate_name"] == "codex-fable5"
    assert next_step["selected_local_lane"] == "test"
    assert next_step["selected_route_profiles"] == ["codex_workflow_gate"]
    assert next_step["validation_target"] == "skill_route_first_probe_regression"
    assert next_step["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow"
    )
    assert next_step["promotion_proof"] == {
        "controller_surface": "skill_route_discovery_promotion_proof",
        "selected_local_lane": "test",
        "target_path_hashes": [
            "sha256:9a38f861c194d9e5e004d0f4837e81c564d6cacca53d5f62e09fe0952684650d",
            "sha256:35e8cf2fc42afff1abd6f9335f74413eac5addc1a1495417739324e0ae26a044",
        ],
        "target_path_count": 2,
        "required_evidence": [
            "changed_file_review",
            "focused_local_validation",
            "rollback_artifact",
            "review_note",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert next_step["ready_candidate_names"] == [
        "codex-fable5",
        "compass-skills",
        "threejs-game-skills",
    ]
    assert next_step["blocked_candidate_names"] == []
    assert next_step["local_validation_required"] is True
    assert next_step["runtime_action"] == "none"
    assert next_step["external_skill_activation_allowed"] is False
    assert next_step["external_harness_execution_allowed"] is False
    assert next_step["provider_runtime_launch_allowed"] is False
    assert next_step["remote_execution_allowed"] is False
    assert next_step["raw_source_url_exported"] is False
    assert next_step["raw_evidence_urls_exported"] is False
    assert next_step["raw_target_paths_exported"] is False
    assert next_step["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in matrix["rows"]}
    assert rows["codex-fable5"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert rows["codex-fable5"]["route_probe_decision"] == "skill_route_discovery_first"
    assert rows["codex-fable5"]["first_route_required"] is True
    assert rows["codex-fable5"]["first_route_confirmed"] is True
    assert rows["codex-fable5"]["selected_local_lane"] == "test"
    assert rows["codex-fable5"]["queued_local_lanes"] == ["documentation", "config", "code_patch"]
    assert rows["codex-fable5"]["validation_gates"] == ["skill_route_discovery_first_before_workflow_gate"]

    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["compass-skills"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert rows["compass-skills"]["route_probe_decision"] == "skill_route_discovery"
    assert rows["compass-skills"]["first_route_required"] is False
    assert rows["compass-skills"]["first_route_confirmed"] is True

    assert rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["threejs-game-skills"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert rows["threejs-game-skills"]["runtime_action"] == "none"
    assert rows["threejs-game-skills"]["external_skill_activation_allowed"] is False

    target_rows = {row["candidate_name"]: row for row in activation_targets["rows"]}
    assert target_rows["codex-fable5"]["selected_local_lane"] == "test"
    assert target_rows["codex-fable5"]["validation_target"] == "skill_route_first_probe_regression"
    assert target_rows["codex-fable5"]["first_route_required"] is True
    assert target_rows["codex-fable5"]["first_route_confirmed"] is True
    assert target_rows["codex-fable5"]["activation_ready"] is True
    assert target_rows["codex-fable5"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow"
    )
    assert target_rows["codex-fable5"]["promotion_proof"]["selected_local_lane"] == "test"
    assert target_rows["codex-fable5"]["promotion_proof"]["target_path_count"] == 2
    assert target_rows["codex-fable5"]["promotion_proof"]["raw_target_paths_exported"] is False

    assert target_rows["compass-skills"]["selected_local_lane"] == "config"
    assert target_rows["compass-skills"]["validation_target"] == "state_or_profile_boundary_metadata"
    assert target_rows["compass-skills"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff"
    )
    assert target_rows["compass-skills"]["promotion_proof"]["selected_local_lane"] == "config"
    assert target_rows["compass-skills"]["promotion_proof"]["target_path_count"] == 1

    assert target_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert target_rows["threejs-game-skills"]["validation_target"] == "local_frontend_render_or_workflow_check"
    assert target_rows["threejs-game-skills"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend"
    )
    assert all(row["runtime_action"] == "none" for row in target_rows.values())
    assert all(row["external_skill_activation_allowed"] is False for row in target_rows.values())
    assert all(row["raw_source_url_exported"] is False for row in target_rows.values())

    completion = lane_map["completion_workflow"]
    assert completion["controller_surface"] == "skill_route_discovery_completion_workflow"
    assert completion["status"] == "ready"
    assert completion["decision"] == "complete_bounded_local_validation_then_external_supervisor_handoff"
    assert completion["candidate_count"] == 3
    assert completion["ready_candidate_count"] == 3
    assert completion["blocked_candidate_count"] == 0
    assert completion["blocked_candidate_names"] == []
    assert completion["selected_local_lanes"] == ["config", "test"]
    assert completion["validation_targets"] == [
        "skill_route_first_probe_regression",
        "state_or_profile_boundary_metadata",
        "local_frontend_render_or_workflow_check",
    ]
    assert completion["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow",
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
    ]
    assert completion["required_evidence"] == [
        "rollback_ref",
        "rollback_artifact",
        "focused_local_validation",
        "changed_file_review",
        "review_note",
    ]
    assert completion["operator_sequence"] == [
        "confirm_rollback_ref_and_artifact_exist",
        "run_replay_commands_for_selected_local_lanes",
        "review_changed_files_and_privacy_panel",
        "leave_activation_to_external_supervisor",
    ]
    assert completion["privacy_review_required"] is True
    assert completion["privacy_review_gate"] == "privacy-leakage-human-review"
    assert completion["privacy_review_candidate_count"] == 1
    assert completion["promotion_readiness_status"] == "ready"
    assert completion["supervisor_handoff"] == "external_supervisor_only"
    assert completion["rollback_ref_required"] is True
    assert completion["rollback_artifact_required"] is True
    assert completion["kernel_self_restart_allowed"] is False
    assert completion["restart_or_remote_activation_required"] is False
    assert completion["promotion_or_push_performed"] is False
    assert completion["local_validation_required"] is True
    assert completion["runtime_action"] == "none"
    assert completion["external_skill_activation_allowed"] is False
    assert completion["external_harness_execution_allowed"] is False
    assert completion["provider_runtime_launch_allowed"] is False
    assert completion["remote_execution_allowed"] is False
    assert completion["raw_source_url_exported"] is False
    assert completion["raw_evidence_urls_exported"] is False
    assert completion["raw_target_paths_exported"] is False
    assert completion["raw_upstream_body_exported"] is False


def test_skill_route_discovery_privacy_review_panel_is_body_free_for_sensitive_profiles():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "provider_runtime_pass2_four_item_evidence.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    panel = lane_map["privacy_review_panel"]
    assert panel["controller_surface"] == "skill_route_discovery_privacy_review_panel"
    assert panel["status"] == "review_required"
    assert panel["decision"] == "keep_privacy_sensitive_skill_routes_review_only_until_boundary_validated"
    assert panel["review_gate"] == "privacy-leakage-human-review"
    assert panel["review_only_risk_flags"] == ["privacy-leakage"]
    assert panel["review_row_count"] == 2
    assert panel["review_candidate_names"] == ["compass-skills", "zhengxi-views"]
    assert panel["runtime_action"] == "none"
    assert panel["profile_write_allowed"] is False
    assert panel["memory_write_allowed"] is False
    assert panel["provider_runtime_launch_allowed"] is False
    assert panel["external_skill_activation_allowed"] is False
    assert panel["external_harness_execution_allowed"] is False
    assert panel["remote_execution_allowed"] is False
    assert panel["raw_source_url_exported"] is False
    assert panel["raw_evidence_urls_exported"] is False
    assert panel["raw_target_paths_exported"] is False
    assert panel["raw_upstream_body_exported"] is False
    assert panel["sensitive_value_export_allowed"] is False

    rows = {row["candidate_name"]: row for row in panel["rows"]}
    assert rows["compass-skills"]["candidate_source_hash"].startswith("sha256:")
    assert rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["compass-skills"]["review_reasons"] == [
        "state_or_profile_boundary",
        "privacy_boundary_required",
        "profile_or_memory_write_denied",
    ]
    assert rows["compass-skills"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]

    assert rows["zhengxi-views"]["candidate_source_hash"].startswith("sha256:")
    assert rows["zhengxi-views"]["route_profiles"] == ["source_cited_domain_research"]
    assert rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert rows["zhengxi-views"]["review_reasons"] == [
        "advice_or_domain_research_boundary",
        "private_context_export_denied",
        "provider_runtime_launch_denied",
    ]
    assert rows["zhengxi-views"]["validation_gates"] == [
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    ]
    assert all("source_url" not in row for row in panel["rows"])
    assert all("evidence_urls" not in row for row in panel["rows"])
    assert all(row["runtime_action"] == "none" for row in panel["rows"])
    assert all(row["sensitive_value_export_allowed"] is False for row in panel["rows"])


def test_skill_route_discovery_validation_profile_coverage_keeps_all_profiles_bounded():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "FableCodex",
                "source_url": "https://github.com/baskduf/FableCodex",
                "summary": "Codex skill workflow gate with review ledger, plugin boundary, tests, and config.",
                "suggested_lanes": ["documentation", "config", "test", "code_patch"],
            },
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "summary": "Skill ecosystem profile handoff with task forest, local memory, privacy boundary, and validation.",
                "suggested_lanes": ["config", "test", "documentation"],
            },
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "summary": "Three.js browser game workflow skills with frontend QA and scaffold tests.",
                "suggested_lanes": ["test", "documentation", "code_patch"],
            },
            {
                "name": "minimal-skill-note",
                "source_url": "https://github.com/example/minimal-skill-note",
                "summary": "Small public agent skill note with local documentation only.",
                "suggested_lanes": ["documentation"],
            },
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)
    coverage = lane_map["validation_profile_coverage"]

    assert coverage["controller_surface"] == "skill_route_discovery_validation_profile_coverage"
    assert coverage["status"] == "ready"
    assert coverage["decision"] == "validation_profiles_have_bounded_local_lanes"
    assert coverage["required_validation_profiles"] == list(SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES)
    assert coverage["ready_validation_profiles"] == list(SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES)
    assert coverage["blocked_validation_profiles"] == []
    assert coverage["ready_profile_count"] == 6
    assert coverage["blocked_profile_count"] == 0
    assert coverage["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert coverage["local_validation_required"] is True
    assert coverage["runtime_action"] == "none"
    assert coverage["external_skill_activation_allowed"] is False
    assert coverage["external_harness_execution_allowed"] is False
    assert coverage["provider_runtime_launch_allowed"] is False
    assert coverage["remote_execution_allowed"] is False
    assert coverage["raw_source_url_exported"] is False
    assert coverage["raw_evidence_urls_exported"] is False
    assert coverage["raw_upstream_body_exported"] is False

    rows = {row["validation_profile"]: row for row in coverage["rows"]}
    assert rows["skill_term"]["candidate_names"] == [
        "compass-skills",
        "FableCodex",
        "minimal-skill-note",
        "threejs-game-skills",
    ]
    assert rows["skill_term"]["signal_basis"] == ["matched_skill_term"]
    assert rows["mixed_skill_workflow_probe"]["candidate_names"] == ["FableCodex"]
    assert rows["mixed_skill_workflow_probe"]["selected_local_lanes"] == ["test"]
    assert rows["mixed_skill_workflow_probe"]["signal_basis"] == ["route_probe_decision"]
    assert rows["generic_skill_workflow"]["candidate_names"] == ["minimal-skill-note"]
    assert rows["generic_skill_workflow"]["selected_local_lanes"] == ["documentation"]
    assert rows["skill_ecosystem_state_handoff"]["candidate_names"] == ["compass-skills"]
    assert rows["skill_ecosystem_state_handoff"]["selected_local_lanes"] == ["config"]
    assert rows["game_frontend_workflow"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["game_frontend_workflow"]["selected_local_lanes"] == ["test"]
    assert rows["codex_workflow_gate"]["candidate_names"] == ["FableCodex"]
    assert rows["codex_workflow_gate"]["selected_local_lanes"] == ["test"]
    for row in coverage["rows"]:
        assert row["status"] == "ready"
        assert set(row["allowed_local_lanes"]) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False


def test_skill_route_discovery_mixed_codex_agent_workflow_probe_routes_first_through_skill_lanes():
    registry = build_skill_route_discovery_registry_from_evidence_items(
        [
            {
                "item_id": "fablecodex-mixed-workflow",
                "item_kind": "repository",
                "name": "FableCodex",
                "source_url": "https://github.com/baskduf/FableCodex",
                "title": "FableCodex Codex agent skill workflow probe",
                "summary": (
                    "Codex plugin and agent workflow skill package with examples, tests, "
                    "evals, evidence gates, and review verification."
                ),
                "route_hints": ["skill_route_discovery"],
                "topics": ["codex", "agent-skills", "workflow", "validation"],
                "suggested_lanes": ["documentation", "config", "test", "code_patch", "agent_harness_eval"],
            }
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["proposal_lane_count"] == 4
    inventory = lane_map["candidate_lane_inventory"][0]
    assert inventory["candidate_name"] == "FableCodex"
    assert inventory["proposal_kinds"] == ["documentation", "config", "test", "code_patch"]
    assert inventory["route_probe_decision"] == "skill_route_discovery_first"
    assert inventory["primary_route"] == "skill_route_discovery"
    assert inventory["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert inventory["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert inventory["agent_harness_eval_allowed_after"] == "local_corroboration_or_general_agent_project_claim"
    assert inventory["full_mixed_signal"] is True
    assert inventory["recommended_local_lane_order"] == ["test", "documentation", "config", "code_patch"]
    assert inventory["local_validation_required"] is True
    assert inventory["runtime_action"] == "none"
    assert inventory["external_skill_activation_allowed"] is False

    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_probe_decision"] == "skill_route_discovery_first" for lane in lane_map["proposal_lanes"])
    assert all(lane["primary_route"] == "skill_route_discovery" for lane in lane_map["proposal_lanes"])
    assert all(lane["full_mixed_signal"] is True for lane in lane_map["proposal_lanes"])
    assert all(
        lane["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
        for lane in lane_map["proposal_lanes"]
    )
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_mixed_codex_workflow_skill_probe_does_not_require_agent_term():
    registry = build_skill_route_discovery_registry_from_evidence_items(
        [
            {
                "item_id": "fablecodex-codex-workflow-skill",
                "item_kind": "repository",
                "name": "FableCodex",
                "source_url": "https://github.com/baskduf/FableCodex",
                "title": "FableCodex Codex skill workflow gate",
                "summary": (
                    "Codex plugin workflow skill package with examples, tests, "
                    "evals, evidence gates, and review verification."
                ),
                "route_hints": ["skill_route_discovery"],
                "topics": ["codex", "skills", "workflow", "validation"],
                "suggested_lanes": [
                    "documentation",
                    "config",
                    "test",
                    "code_patch",
                    "agent_harness_eval",
                ],
            }
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["proposal_lane_count"] == 4
    inventory = lane_map["candidate_lane_inventory"][0]
    assert inventory["route_probe_decision"] == "skill_route_discovery_first"
    assert inventory["primary_route"] == "skill_route_discovery"
    assert inventory["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert inventory["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert inventory["full_mixed_signal"] is False
    assert inventory["proposal_kinds"] == ["documentation", "config", "test", "code_patch"]
    assert inventory["local_validation_required"] is True
    assert inventory["runtime_action"] == "none"
    assert inventory["external_skill_activation_allowed"] is False
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_probe_decision"] == "skill_route_discovery_first" for lane in lane_map["proposal_lanes"])
    assert all(lane["full_mixed_signal"] is False for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_proposal_lane_map_cites_only_item_evidence_urls():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "fablecodex_issue_evidence_items.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])
    registry["candidates"][0]["evidence_urls"].append("https://github.com/example/non-item-evidence")

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["proposal_lane_count"] == 4
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(
        lane["evidence_urls"]
        == [
            "https://github.com/baskduf/FableCodex",
            "https://github.com/baskduf/FableCodex/issues/15",
            "https://github.com/baskduf/FableCodex/issues/18",
        ]
        for lane in lane_map["proposal_lanes"]
    )
    assert all(
        lane["evidence_item_ids"]
        == [
            "fablecodex-repo",
            "fablecodex-issue-15",
            "fablecodex-issue-15-repeat",
            "fablecodex-issue-18",
        ]
        for lane in lane_map["proposal_lanes"]
    )
    assert all("https://github.com/example/non-item-evidence" not in lane["evidence_urls"] for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_current_window_skill_workflow_signals_stay_classification_only():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "provider_runtime_pass2_four_item_evidence.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 4
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert lane_map["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
    assert lane_map["allowed_proposal_kinds"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane_map["proposal_lane_count"] == 16
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    inventory_by_name = {row["candidate_name"]: row for row in lane_map["candidate_lane_inventory"]}
    expected_profiles = {
        "FableCodex": ["codex_workflow_gate"],
        "compass-skills": ["skill_ecosystem_state_handoff"],
        "threejs-game-skills": ["game_frontend_workflow"],
        "zhengxi-views": ["source_cited_domain_research"],
    }
    expected_selected_lanes = {
        "FableCodex": "test",
        "compass-skills": "config",
        "threejs-game-skills": "test",
        "zhengxi-views": "test",
    }

    assert set(candidates_by_name) == set(expected_profiles)
    for name, expected_profile in expected_profiles.items():
        candidate = candidates_by_name[name]
        inventory = inventory_by_name[name]
        assert candidate["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert candidate["route_hints"] == ["skill_route_discovery"]
        assert set(candidate["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert candidate["requested_actions"] == []
        assert candidate["route_profiles"] == expected_profile
        assert inventory["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert inventory["route_profiles"] == expected_profile
        assert inventory["proposal_kinds"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert inventory["handoff_metadata"]["selected_local_lane"] == expected_selected_lanes[name]
        assert inventory["runtime_action"] == "none"
        assert inventory["external_skill_activation_allowed"] is False

    for lane in lane_map["proposal_lanes"]:
        assert lane["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert lane["route_hint"] == "skill_route_discovery"
        assert lane["proposal_kind"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        assert lane["runtime_action"] == "none"
        assert lane["external_skill_activation_allowed"] is False
        assert lane["provider_runtime_launch_allowed"] is False
        assert lane["local_validation_required"] is True


def test_skill_route_discovery_proposal_lane_map_downgrades_unsupported_lanes():
    registry = build_skill_route_discovery_registry(
        [
            ExternalSkillRouteCandidate(
                name="lane-overreach",
                source_url="https://github.com/example/lane-overreach",
                candidate_lanes=("documentation", "runtime_execution", "install"),
            )
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["source_registry_status"] == "invalid_candidates_present"
    assert lane_map["proposal_lane_count"] == 1
    assert lane_map["proposal_lanes"][0]["proposal_kind"] == "documentation"
    assert lane_map["proposal_lanes"][0]["runtime_action"] == "none"
    assert lane_map["candidate_lane_inventory"] == [
        {
            "candidate_name": "lane-overreach",
            "source_url": "https://github.com/example/lane-overreach",
            "proposal_kinds": ["documentation"],
            "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
            "route_profiles": ["generic_skill_workflow"],
            "matched_route_terms": [],
            "discovery_event_kind": "unknown",
            "discovery_event_effect": "record_only",
            "evidence_item_ids": [],
            "evidence_urls": ["https://github.com/example/lane-overreach"],
            "route_validation_contract": {
                "controller_surface": "skill_route_discovery_route_validation_contract",
                "status": "ready",
                "route_profiles": ["generic_skill_workflow"],
                "allowed_local_lanes": ["documentation"],
                "row_count": 1,
                "rows": [
                    {
                        "route_profile": "generic_skill_workflow",
                        "validation_gate": "generic_skill_workflow_local_validation_before_activation",
                        "allowed_local_lanes": ["documentation"],
                        "preferred_local_lanes": ["documentation"],
                        "required_metadata": [
                            "selected_digest_item_ids_or_frozen_digest_evidence",
                            "body_free_repository_summary",
                            "local_artifact_target",
                        ],
                        "blocked_activation_reason": "generic_skill_evidence_requires_local_corroboration",
                        "local_validation_required": True,
                        "runtime_action": "none",
                        "external_skill_activation_allowed": False,
                        "raw_upstream_body_exported": False,
                    }
                ],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_activation_allowed": False,
                "provider_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_upstream_body_exported": False,
            },
            "handoff_metadata": {
                "controller_surface": "skill_route_discovery_lane_handoff_metadata",
                "handoff_scope": "candidate_inventory",
                "status": "ready",
                "decision": "handoff_bounded_local_lane_for_validation",
                "route_profiles": ["generic_skill_workflow"],
                "allowed_local_lanes": ["documentation"],
                "selected_local_lane": "documentation",
                "queued_local_lanes": [],
                "validation_gates": ["generic_skill_workflow_local_validation_before_activation"],
                "required_metadata": [
                    "selected_digest_item_ids_or_frozen_digest_evidence",
                    "body_free_repository_summary",
                    "local_artifact_target",
                ],
                "activation_gate": "local_validation_before_activation",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_upstream_body_exported": False,
            },
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "activation_gate": "local_validation_before_activation",
            "uncertainty": (
                "External skill evidence is unvalidated repository-level routing evidence; keep proposals local, "
                "bounded, and separately validated."
            ),
            "uncertainty_reasons": [
                "unvalidated_external_skill_evidence",
                "single_repository_level_source",
                "no_selected_digest_item_ids",
            ],
        }
    ]
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 1
    assert lane_map["downgraded_candidates"][0] == {
        "name": "lane-overreach",
        "source_url": "https://github.com/example/lane-overreach",
        "status": "downgraded_candidate",
        "allowed_lanes": ["documentation"],
        "rejected_lanes": ["install", "runtime_execution"],
        "reason": "unsupported_candidate_lanes_removed",
        "validation_errors": ["unsupported_candidate_lanes:install,runtime_execution"],
    }


def test_skill_route_discovery_proposal_lane_map_rejects_actionful_or_unsafe_candidates():
    registry = build_skill_route_discovery_registry(
        [
            ExternalSkillRouteCandidate(
                name="actionful-skill",
                source_url="https://github.com/example/actionful-skill",
                candidate_lanes=("documentation", "code_patch"),
                requested_actions=("install",),
            ),
            ExternalSkillRouteCandidate(
                name="private-host-skill",
                source_url="https://git.internal.example/team/private-skill",
                candidate_lanes=("test",),
            ),
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert lane_map["proposal_lane_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0
    assert lane_map["rejected_candidate_count"] == 2
    assert [candidate["name"] for candidate in lane_map["rejected_candidates"]] == [
        "actionful-skill",
        "private-host-skill",
    ]
    assert [candidate["reason"] for candidate in lane_map["rejected_candidates"]] == [
        "candidate_has_non_lane_validation_errors",
        "candidate_has_non_lane_validation_errors",
    ]
