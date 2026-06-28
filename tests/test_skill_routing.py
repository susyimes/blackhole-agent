import json
from pathlib import Path

from blackhole_agent.skill_routing import (
    AMBIGUOUS_SKILL_MATCH,
    EXACT_TRIGGER_MATCH,
    SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
    SKILL_ROUTE_DISCOVERY_DISABLED,
    SKILL_ROUTE_DISCOVERY_HINT,
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
    build_skill_route_discovery_registry_validation_lane,
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


def test_skill_route_discovery_registry_validation_lane_checks_route_availability():
    registry = build_skill_route_discovery_registry(
        [
            ExternalSkillRouteCandidate(
                name="compass-skills",
                source_url="https://github.com/dongshuyan/compass-skills",
                evidence_summary="Skill ecosystem state handoff profiles and config metadata.",
                candidate_lanes=("config", "test"),
            ),
            ExternalSkillRouteCandidate(
                name="threejs-game-skills",
                source_url="https://github.com/majidmanzarpour/threejs-game-skills",
                evidence_summary="Three.js browser game skill workflow with validation checks.",
                candidate_lanes=("test", "code_patch"),
            ),
        ]
    )

    validation_lane = build_skill_route_discovery_registry_validation_lane(registry)
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert validation_lane["controller_surface"] == "skill_route_discovery_registry_validation_lane"
    assert validation_lane["status"] == "ready"
    assert validation_lane["decision"] == "skill_route_registry_ready_for_local_lane_mapping"
    assert validation_lane["diagnostics"] == []
    assert validation_lane["candidate_count"] == 2
    assert validation_lane["available_route_count"] == 2
    assert validation_lane["unavailable_route_count"] == 0
    assert validation_lane["validation_gate"] == "skill_route_discovery_registry_validation_before_activation"
    assert validation_lane["runtime_action"] == "none"
    assert validation_lane["external_skill_activation_allowed"] is False
    assert lane_map["registry_validation_lane"] == validation_lane

    rows_by_name = {row["candidate_name"]: row for row in validation_lane["rows"]}
    assert rows_by_name["compass-skills"]["route_available"] is True
    assert rows_by_name["compass-skills"]["route_hint_available"] is True
    assert rows_by_name["compass-skills"]["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
    assert rows_by_name["compass-skills"]["route_status"] == SKILL_ROUTE_DISCOVERY_DISABLED
    assert rows_by_name["compass-skills"]["allowed_candidate_lanes"] == ["config", "test"]
    assert "skill_ecosystem_state_handoff" in rows_by_name["compass-skills"]["route_profiles"]
    assert rows_by_name["threejs-game-skills"]["allowed_candidate_lanes"] == ["test", "code_patch"]
    assert "game_frontend_workflow" in rows_by_name["threejs-game-skills"]["route_profiles"]


def test_skill_route_discovery_registry_validation_lane_reports_malformed_records():
    registry = build_skill_route_discovery_registry(
        [
            ExternalSkillRouteCandidate(
                name="enabled-route",
                source_url="https://github.com/example/enabled-route",
                candidate_lanes=("documentation", "runtime_execution"),
                enabled=True,
            )
        ]
    )
    registry["candidate_count"] = 3
    registry["candidates"].append(
        {
            "name": "missing-route-metadata",
            "source_url": "https://github.com/example/missing-route-metadata",
            "candidate_lanes": ["documentation"],
            "route_hints": [],
            "validation_errors": [],
            "enabled": False,
        }
    )
    registry["candidates"].append("not-a-candidate")

    validation_lane = build_skill_route_discovery_registry_validation_lane(registry)

    assert validation_lane["status"] == "blocked"
    assert validation_lane["decision"] == "repair_skill_route_registry_before_lane_activation"
    assert validation_lane["candidate_count"] == 3
    assert validation_lane["available_route_count"] == 0
    assert validation_lane["unavailable_route_count"] == 3
    assert validation_lane["runtime_action"] == "none"
    assert validation_lane["external_skill_activation_allowed"] is False
    assert validation_lane["external_harness_execution_allowed"] is False
    assert validation_lane["diagnostics"] == [
        (
            "candidates[0].validation_errors:"
            "external_skill_route_candidates_must_start_disabled,"
            "unsupported_candidate_lanes:runtime_execution"
        ),
        "candidates[0].enabled_must_be_false",
        "candidates[1].route_class_missing",
        "candidates[1].route_status_missing",
        "candidates[1].route_profiles_missing",
        "candidates[1].route_hints_missing_skill_route_discovery",
        "candidates[1].route_class_mismatch",
        "candidates[1].route_status_must_be_disabled_or_invalid",
        "candidates[2].entry_must_be_an_object",
    ]
    assert validation_lane["rows"][0]["validation_error_count"] == 2
    assert validation_lane["rows"][0]["route_available"] is False
    assert validation_lane["rows"][1]["diagnostics"] == [
        "candidates[1].route_class_missing",
        "candidates[1].route_status_missing",
        "candidates[1].route_profiles_missing",
        "candidates[1].route_hints_missing_skill_route_discovery",
        "candidates[1].route_class_mismatch",
        "candidates[1].route_status_must_be_disabled_or_invalid",
    ]


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


def test_skill_route_discovery_current_pass_skill_routes_ignore_activity_pressure():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass1_skill_route_lanes.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry(payload["candidates"])
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 3
    assert lane_map["candidate_count"] == 3
    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["downgraded_candidate_count"] == 3
    assert lane_map["rejected_candidate_count"] == 0

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    assert candidates_by_name["threejs-game-skills"]["route_hints"] == ["skill_route_discovery"]
    assert candidates_by_name["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert candidates_by_name["threejs-game-skills"]["public_activity_signals"] == [
        "stars_present",
        "forks_present",
    ]
    assert candidates_by_name["zhengxi-views"]["route_profiles"] == ["generic_skill_workflow"]
    assert candidates_by_name["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]

    inventory_by_name = {row["candidate_name"]: row for row in lane_map["candidate_lane_inventory"]}
    assert set(inventory_by_name) == {"zhengxi-views", "threejs-game-skills", "compass-skills"}
    assert all(
        set(row["proposal_kinds"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        for row in inventory_by_name.values()
    )
    assert all(row["runtime_action"] == "none" for row in inventory_by_name.values())
    assert all(row["external_skill_activation_allowed"] is False for row in inventory_by_name.values())
    assert all(
        row["public_activity_policy"]["effect"] == "supporting_context_only_no_runtime_action"
        for row in inventory_by_name.values()
    )
    assert all(
        row["public_activity_policy"]["proposal_lane_count_effect"] == "none"
        for row in inventory_by_name.values()
    )
    game_contract_row = inventory_by_name["threejs-game-skills"]["route_validation_contract"]["rows"][0]
    assert game_contract_row["route_profile"] == "game_frontend_workflow"
    assert game_contract_row["validation_gate"] == "local_frontend_validation_before_game_skill_activation"
    assert game_contract_row["preferred_local_lanes"] == ["test", "documentation", "code_patch", "config"]
    assert game_contract_row["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert game_contract_row["blocked_activation_reason"] == (
        "upstream_scaffold_or_provider_boundary_not_validated"
    )
    assert game_contract_row["local_validation_required"] is True
    assert game_contract_row["runtime_action"] == "none"
    assert game_contract_row["external_skill_activation_allowed"] is False
    assert inventory_by_name["threejs-game-skills"]["handoff_metadata"]["selected_local_lane"] == "test"
    assert inventory_by_name["compass-skills"]["handoff_metadata"]["selected_local_lane"] == "config"
    assert inventory_by_name["compass-skills"]["state_profile_boundary"]["memory_write_allowed"] is False

    for lane in lane_map["proposal_lanes"]:
        assert lane["proposal_kind"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        assert lane["evidence_item_ids"]
        assert lane["runtime_action"] == "none"
        assert lane["external_skill_activation_allowed"] is False
        assert lane["provider_runtime_launch_allowed"] is False
        assert lane["public_activity_policy"]["activation_readiness_effect"] == "none"


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

    pass2_handoff = lane_map["pass2_validation_handoff"]
    assert pass2_handoff["controller_surface"] == "skill_route_discovery_pass2_validation_handoff"
    assert pass2_handoff["status"] == "ready"
    assert pass2_handoff["decision"] == "handoff_pass2_profiles_to_bounded_local_validation"
    assert pass2_handoff["candidate_count"] == 4
    assert pass2_handoff["route_profile_count"] == 4
    assert pass2_handoff["blocked_candidate_names"] == []
    assert pass2_handoff["observed_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert pass2_handoff["selected_local_lanes"] == ["config", "test"]
    assert pass2_handoff["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert pass2_handoff["validation_targets"] == [
        "skill_route_first_probe_regression",
        "state_or_profile_boundary_metadata",
        "source_citation_and_advice_boundary_check",
        "local_frontend_render_or_workflow_check",
    ]
    assert pass2_handoff["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow",
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
        "python -m pytest tests/test_skill_routing.py -q -k source_cited_domain_research",
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
    ]
    assert pass2_handoff["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "rollback_artifact",
        "focused_local_validation",
        "changed_file_review",
        "review_note",
    ]
    assert pass2_handoff["local_validation_required"] is True
    assert pass2_handoff["runtime_action"] == "none"
    assert pass2_handoff["external_skill_activation_allowed"] is False
    assert pass2_handoff["external_agent_activation_allowed"] is False
    assert pass2_handoff["external_harness_execution_allowed"] is False
    assert pass2_handoff["provider_runtime_launch_allowed"] is False
    assert pass2_handoff["remote_execution_allowed"] is False
    assert pass2_handoff["raw_source_url_exported"] is False
    assert pass2_handoff["raw_evidence_urls_exported"] is False
    assert pass2_handoff["raw_target_paths_exported"] is False
    assert pass2_handoff["raw_upstream_body_exported"] is False

    pass2_rows = {row["candidate_name"]: row for row in pass2_handoff["rows"]}
    assert pass2_rows["compass-skills"]["selected_local_lane"] == "config"
    assert pass2_rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert pass2_rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert pass2_rows["zhengxi-views"]["route_profiles"] == ["source_cited_domain_research"]
    assert pass2_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert pass2_rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert all(set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES) for row in pass2_rows.values())
    assert all(row["skill_route_discovery_inherited"] is True for row in pass2_rows.values())
    assert all(row["agent_harness_eval_required"] is False for row in pass2_rows.values())
    assert all(row["runtime_action"] == "none" for row in pass2_rows.values())
    assert all(row["external_skill_activation_allowed"] is False for row in pass2_rows.values())
    assert all(row["external_harness_execution_allowed"] is False for row in pass2_rows.values())

    adjacent_policy = pass2_handoff["adjacent_general_agent_policy"]
    assert adjacent_policy == {
        "primary_route": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes": ["documentation", "test", "code_patch"],
        "required_before_implementation": "local_agent_harness_eval",
        "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_upstream_body_exported": False,
    }

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


def test_skill_route_discovery_current_window_pass1_proposal_intake_is_bounded():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass1_proposal_intake.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_summaries(payload["summaries"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert lane_map["proposal_lane_count"] == 12

    intake = lane_map["proposal_intake_lane"]
    assert intake["controller_surface"] == "skill_route_discovery_proposal_intake_lane"
    assert intake["status"] == "ready"
    assert intake["decision"] == "current_window_proposals_mapped_to_bounded_local_lanes"
    assert intake["proposal_count"] == 3
    assert intake["ready_proposal_count"] == 3
    assert intake["blocked_proposal_ids"] == []
    assert intake["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert intake["required_evidence"] == [
        "body_free_repository_summary",
        "route_hints",
        "focused_local_validation",
        "rollback_artifact",
    ]
    assert intake["local_validation_required"] is True
    assert intake["runtime_action"] == "none"
    assert intake["external_skill_activation_allowed"] is False
    assert intake["external_harness_execution_allowed"] is False
    assert intake["provider_runtime_launch_allowed"] is False
    assert intake["remote_execution_allowed"] is False
    assert intake["raw_source_url_exported"] is False
    assert intake["raw_evidence_urls_exported"] is False
    assert intake["raw_target_paths_exported"] is False
    assert intake["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in intake["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-handoff",
    }
    assert rows["p1-skill-route-discovery-generic"]["proposal_track"] == "generic_python_skill_repository"
    assert rows["p1-skill-route-discovery-generic"]["candidate_names"] == ["zhengxi-views"]
    assert rows["p1-skill-route-discovery-generic"]["route_profiles"] == ["source_cited_domain_research"]
    assert rows["p1-skill-route-discovery-generic"]["selected_local_lanes"] == ["test"]
    assert rows["p1-skill-route-discovery-generic"]["validation_targets"] == [
        "source_citation_and_advice_boundary_check"
    ]
    assert rows["p1-skill-route-discovery-generic"]["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k source_cited_domain_research"
    ]

    assert rows["p2-game-frontend-skill-profile"]["proposal_track"] == "game_frontend_workflow"
    assert rows["p2-game-frontend-skill-profile"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["p2-game-frontend-skill-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p2-game-frontend-skill-profile"]["selected_local_lanes"] == ["test"]
    assert rows["p2-game-frontend-skill-profile"]["validation_targets"] == [
        "local_frontend_render_or_workflow_check"
    ]

    assert rows["p3-skill-ecosystem-handoff"]["proposal_track"] == "skill_ecosystem_state_handoff"
    assert rows["p3-skill-ecosystem-handoff"]["candidate_names"] == ["compass-skills"]
    assert rows["p3-skill-ecosystem-handoff"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows["p3-skill-ecosystem-handoff"]["selected_local_lanes"] == ["config"]
    assert rows["p3-skill-ecosystem-handoff"]["validation_targets"] == [
        "state_or_profile_boundary_metadata"
    ]

    for row in rows.values():
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False

    validation_cases = lane_map["current_pass_validation_cases"]
    assert validation_cases["controller_surface"] == "skill_route_discovery_current_pass_validation_cases"
    assert validation_cases["status"] == "ready"
    assert validation_cases["decision"] == "current_pass_skill_route_cases_ready_for_bounded_local_validation"
    assert validation_cases["review_gate"] == "focused-evidence-review"
    assert validation_cases["proposal_count"] == 3
    assert validation_cases["ready_proposal_count"] == 3
    assert validation_cases["blocked_proposal_ids"] == []
    assert validation_cases["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert validation_cases["required_evidence"] == [
        "body_free_repository_summary",
        "matched_skill_or_agent_topics",
        "focused_local_validation",
        "rollback_artifact",
    ]
    assert validation_cases["runtime_action"] == "none"
    assert validation_cases["external_skill_activation_allowed"] is False
    assert validation_cases["external_harness_execution_allowed"] is False
    assert validation_cases["provider_runtime_launch_allowed"] is False
    assert validation_cases["remote_execution_allowed"] is False
    assert validation_cases["raw_source_url_exported"] is False
    assert validation_cases["raw_evidence_urls_exported"] is False
    assert validation_cases["raw_target_paths_exported"] is False
    assert validation_cases["raw_upstream_body_exported"] is False

    case_rows = {row["proposal_id"]: row for row in validation_cases["rows"]}
    assert set(case_rows) == {
        "p1_skill_route_discovery_generic_views",
        "p2_skill_route_discovery_game_frontend",
        "p3_skill_ecosystem_state_handoff_config",
    }
    assert case_rows["p1_skill_route_discovery_generic_views"]["proposal_kind"] == "test"
    assert case_rows["p1_skill_route_discovery_generic_views"]["proposal_track"] == (
        "generic_python_skill_repository"
    )
    assert case_rows["p1_skill_route_discovery_generic_views"]["candidate_names"] == ["zhengxi-views"]
    assert case_rows["p1_skill_route_discovery_generic_views"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert case_rows["p1_skill_route_discovery_generic_views"]["selected_local_lane"] == "test"

    assert case_rows["p2_skill_route_discovery_game_frontend"]["proposal_kind"] == "documentation"
    assert case_rows["p2_skill_route_discovery_game_frontend"]["candidate_names"] == [
        "threejs-game-skills"
    ]
    assert case_rows["p2_skill_route_discovery_game_frontend"]["route_profiles"] == [
        "game_frontend_workflow"
    ]
    assert case_rows["p2_skill_route_discovery_game_frontend"]["selected_local_lane"] == "documentation"
    assert case_rows["p2_skill_route_discovery_game_frontend"]["validation_target"] == (
        "document_game_frontend_workflow_boundary"
    )

    assert case_rows["p3_skill_ecosystem_state_handoff_config"]["proposal_kind"] == "config"
    assert case_rows["p3_skill_ecosystem_state_handoff_config"]["candidate_names"] == [
        "compass-skills"
    ]
    assert case_rows["p3_skill_ecosystem_state_handoff_config"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert case_rows["p3_skill_ecosystem_state_handoff_config"]["selected_local_lane"] == "config"
    assert case_rows["p3_skill_ecosystem_state_handoff_config"]["validation_target"] == (
        "state_or_profile_boundary_metadata"
    )

    for row in case_rows.values():
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    pass3_handoff = lane_map["pass3_activation_handoff"]
    assert pass3_handoff["controller_surface"] == "skill_route_discovery_pass3_activation_handoff"
    assert pass3_handoff["status"] == "ready"
    assert pass3_handoff["decision"] == "pass3_skill_route_handoff_ready_for_supervisor_replay"
    assert pass3_handoff["capability_pass"] == 3
    assert pass3_handoff["total_passes"] == 4
    assert pass3_handoff["review_gate"] == "focused-evidence-review"
    assert pass3_handoff["proposal_ids"] == [
        "p1-skill-route-discovery-zhengxi-views",
        "p2-game-frontend-skill-route",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert pass3_handoff["ready_proposal_count"] == 3
    assert pass3_handoff["blocked_proposal_ids"] == []
    assert pass3_handoff["focused_review_status"] == "ready"
    assert pass3_handoff["focused_review_blocked_proposal_ids"] == []
    assert pass3_handoff["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert pass3_handoff["selected_local_lanes"] == ["test", "documentation", "config"]
    assert pass3_handoff["recovery_workflow"] == "run_replay_commands_then_recheck_pass3_activation_handoff"
    assert pass3_handoff["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert pass3_handoff["local_validation_required"] is True
    assert pass3_handoff["runtime_action"] == "none"
    assert pass3_handoff["external_skill_activation_allowed"] is False
    assert pass3_handoff["external_harness_execution_allowed"] is False
    assert pass3_handoff["provider_runtime_launch_allowed"] is False
    assert pass3_handoff["remote_execution_allowed"] is False
    assert pass3_handoff["profile_write_allowed"] is False
    assert pass3_handoff["memory_write_allowed"] is False
    assert pass3_handoff["raw_source_url_exported"] is False
    assert pass3_handoff["raw_evidence_urls_exported"] is False
    assert pass3_handoff["raw_target_paths_exported"] is False
    assert pass3_handoff["raw_upstream_body_exported"] is False

    handoff_rows = {row["proposal_id"]: row for row in pass3_handoff["rows"]}
    assert set(handoff_rows) == set(pass3_handoff["proposal_ids"])
    assert handoff_rows["p1-skill-route-discovery-zhengxi-views"]["source_case_id"] == (
        "p1_skill_route_discovery_generic_views"
    )
    assert handoff_rows["p1-skill-route-discovery-zhengxi-views"]["candidate_names"] == ["zhengxi-views"]
    assert handoff_rows["p1-skill-route-discovery-zhengxi-views"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert handoff_rows["p1-skill-route-discovery-zhengxi-views"]["selected_local_lane"] == "test"
    assert handoff_rows["p2-game-frontend-skill-route"]["candidate_names"] == ["threejs-game-skills"]
    assert handoff_rows["p2-game-frontend-skill-route"]["route_profiles"] == ["game_frontend_workflow"]
    assert handoff_rows["p2-game-frontend-skill-route"]["selected_local_lane"] == "documentation"
    assert handoff_rows["p3-skill-ecosystem-state-handoff"]["candidate_names"] == ["compass-skills"]
    assert handoff_rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert handoff_rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "config"

    for row in handoff_rows.values():
        assert row["status"] == "ready"
        assert row["activation_decision"] == "ready_for_supervisor_replay"
        assert row["activation_blockers"] == []
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    preflight_queue = lane_map["pass3_preflight_queue"]
    assert preflight_queue["controller_surface"] == "skill_route_discovery_pass3_preflight_queue"
    assert preflight_queue["status"] == "blocked"
    assert preflight_queue["decision"] == "repair_pass3_skill_route_preflight_before_final_pass"
    assert preflight_queue["capability_pass"] == 3
    assert preflight_queue["total_passes"] == 4
    assert preflight_queue["route_index_status"] == "blocked"
    assert preflight_queue["activation_handoff_status"] == "ready"
    assert preflight_queue["required_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert preflight_queue["observed_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert preflight_queue["missing_route_profiles"] == []
    assert preflight_queue["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert preflight_queue["selected_local_lanes"] == ["test", "documentation", "config"]
    assert set(preflight_queue["queue_blockers"]) == {
        "p1_skill_route_discovery_index:missing_selected_item_ids_or_frozen_fixture",
        "p1_skill_route_discovery_index:route_index_row_not_ready",
        "p2_skill_workflow_docs:missing_selected_item_ids_or_frozen_fixture",
        "p2_skill_workflow_docs:route_index_row_not_ready",
        "p3_skill_route_metadata_config:missing_selected_item_ids_or_frozen_fixture",
        "p3_skill_route_metadata_config:route_index_row_not_ready",
    }
    assert preflight_queue["row_count"] == 3
    assert preflight_queue["ready_row_count"] == 0
    assert preflight_queue["blocked_proposal_ids"] == [
        "p1_skill_route_discovery_index",
        "p2_skill_workflow_docs",
        "p3_skill_route_metadata_config",
    ]
    assert preflight_queue["required_evidence"] == [
        "pass3_route_discovery_index",
        "pass3_activation_handoff",
        "selected_item_ids_or_frozen_fixture",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert preflight_queue["runtime_action"] == "none"
    assert preflight_queue["external_skill_activation_allowed"] is False
    assert preflight_queue["external_harness_execution_allowed"] is False
    assert preflight_queue["provider_runtime_launch_allowed"] is False
    assert preflight_queue["remote_execution_allowed"] is False
    assert preflight_queue["profile_write_allowed"] is False
    assert preflight_queue["memory_write_allowed"] is False
    assert preflight_queue["raw_source_url_exported"] is False
    assert preflight_queue["raw_evidence_urls_exported"] is False
    assert preflight_queue["raw_target_paths_exported"] is False
    assert preflight_queue["raw_upstream_body_exported"] is False

    queue_rows = {row["proposal_id"]: row for row in preflight_queue["rows"]}
    assert queue_rows["p1_skill_route_discovery_index"]["candidate_names"] == ["zhengxi-views"]
    assert queue_rows["p1_skill_route_discovery_index"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert queue_rows["p1_skill_route_discovery_index"]["selected_local_lane"] == "test"
    assert queue_rows["p2_skill_workflow_docs"]["candidate_names"] == [
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert queue_rows["p2_skill_workflow_docs"]["selected_local_lane"] == "documentation"
    assert queue_rows["p3_skill_route_metadata_config"]["candidate_names"] == ["compass-skills"]
    assert queue_rows["p3_skill_route_metadata_config"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert queue_rows["p3_skill_route_metadata_config"]["selected_local_lane"] == "config"

    for row in queue_rows.values():
        assert row["status"] == "blocked"
        assert row["queue_decision"] == "blocked_before_final_pass_replay"
        assert set(row["activation_blockers"]) == {
            "missing_selected_item_ids_or_frozen_fixture",
            "route_index_row_not_ready",
        }
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False


def test_skill_route_discovery_current_pass_validation_cases_accept_generic_python_skill_signal():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "python-agent-skill-workflow",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "summary": (
                    "Public Python agent skill workflow repository with SKILL.md, route metadata, "
                    "local validation tests, and documentation examples."
                ),
                "topics": ["agent", "skill", "python", "workflow"],
                "suggested_lanes": ["documentation", "config", "test", "code_patch", "install"],
                "observed_paths": [
                    "SKILL.md",
                    "skills/zhengxi-views/SKILL.md",
                    "tests/test_skill_route.py",
                    "scripts/validate_skill.py",
                ],
                "metadata_files": ["skill.yml"],
            }
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    candidate = registry["candidates"][0]
    assert candidate["route_hints"] == ["skill_route_discovery"]
    assert candidate["route_profiles"] == ["generic_skill_workflow"]
    assert set(candidate["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert candidate["matched_route_terms"] == ["agent", "skill", "workflow"]
    assert candidate["requested_actions"] == []
    assert candidate["enabled"] is False
    assert candidate["validation_errors"] == []

    assert lane_map["proposal_lane_count"] == 4
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_hint"] == "skill_route_discovery" for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["external_skill_activation_allowed"] is False for lane in lane_map["proposal_lanes"])
    assert all(lane["provider_runtime_launch_allowed"] is False for lane in lane_map["proposal_lanes"])

    validation_cases = lane_map["current_pass_validation_cases"]
    rows = {row["proposal_id"]: row for row in validation_cases["rows"]}
    assert validation_cases["status"] == "blocked"
    assert validation_cases["blocked_proposal_ids"] == [
        "p2_skill_route_discovery_game_frontend",
        "p3_skill_ecosystem_state_handoff_config",
    ]
    assert rows["p1_skill_route_discovery_generic_views"]["status"] == "ready"
    assert rows["p1_skill_route_discovery_generic_views"]["candidate_names"] == [
        "python-agent-skill-workflow"
    ]
    assert rows["p1_skill_route_discovery_generic_views"]["route_profiles"] == ["generic_skill_workflow"]
    assert rows["p1_skill_route_discovery_generic_views"]["selected_local_lane"] == "test"
    assert set(rows["p1_skill_route_discovery_generic_views"]["allowed_local_lanes"]) == set(
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    )
    assert rows["p1_skill_route_discovery_generic_views"]["runtime_action"] == "none"
    assert rows["p1_skill_route_discovery_generic_views"]["external_skill_activation_allowed"] is False
    assert rows["p1_skill_route_discovery_generic_views"]["external_harness_execution_allowed"] is False
    assert rows["p1_skill_route_discovery_generic_views"]["provider_runtime_launch_allowed"] is False
    assert rows["p1_skill_route_discovery_generic_views"]["remote_execution_allowed"] is False

    pass3_handoff = lane_map["pass3_activation_handoff"]
    assert pass3_handoff["status"] == "blocked"
    assert pass3_handoff["decision"] == "repair_pass3_skill_route_handoff_before_activation"
    assert pass3_handoff["ready_proposal_count"] == 1
    assert pass3_handoff["blocked_proposal_ids"] == [
        "p2-game-frontend-skill-route",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert pass3_handoff["recovery_workflow"] == "repair_blocked_rows_then_rerun_current_pass_validation_cases"
    handoff_rows = {row["proposal_id"]: row for row in pass3_handoff["rows"]}
    assert handoff_rows["p1-skill-route-discovery-zhengxi-views"]["activation_decision"] == (
        "ready_for_supervisor_replay"
    )
    assert handoff_rows["p2-game-frontend-skill-route"]["activation_decision"] == "blocked_before_activation"
    assert handoff_rows["p2-game-frontend-skill-route"]["activation_blockers"] == [
        "current_pass_validation_case_not_ready",
        "missing_candidate_evidence",
        "missing_selected_local_lane",
    ]
    assert pass3_handoff["runtime_action"] == "none"
    assert pass3_handoff["external_skill_activation_allowed"] is False
    assert pass3_handoff["provider_runtime_launch_allowed"] is False
    assert pass3_handoff["remote_execution_allowed"] is False

    preflight_queue = lane_map["pass3_preflight_queue"]
    assert preflight_queue["status"] == "blocked"
    assert preflight_queue["decision"] == "repair_pass3_skill_route_preflight_before_final_pass"
    assert preflight_queue["route_index_status"] == "blocked"
    assert preflight_queue["activation_handoff_status"] == "blocked"
    assert preflight_queue["observed_route_profiles"] == []
    assert preflight_queue["missing_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert preflight_queue["blocked_proposal_ids"] == [
        "p1_skill_route_discovery_index",
        "p2_skill_workflow_docs",
        "p3_skill_route_metadata_config",
    ]
    assert "missing_required_route_profiles:source_cited_domain_research,game_frontend_workflow,skill_ecosystem_state_handoff" in (
        preflight_queue["queue_blockers"]
    )
    assert preflight_queue["runtime_action"] == "none"
    assert preflight_queue["external_skill_activation_allowed"] is False
    assert preflight_queue["provider_runtime_launch_allowed"] is False
    assert preflight_queue["remote_execution_allowed"] is False


def test_skill_route_discovery_pass3_route_discovery_index_bounds_active_profiles():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass3_skill_route_index.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 3
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0

    index = lane_map["pass3_route_discovery_index"]
    assert index["controller_surface"] == "skill_route_discovery_pass3_route_discovery_index"
    assert index["status"] == "ready"
    assert index["decision"] == "pass3_skill_route_profiles_indexed_for_bounded_local_validation"
    assert index["capability_pass"] == 3
    assert index["total_passes"] == 4
    assert index["review_gate"] == "focused-evidence-review"
    assert index["proposal_count"] == 3
    assert index["ready_proposal_count"] == 3
    assert index["blocked_proposal_ids"] == []
    assert index["observed_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert index["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert index["selected_local_lanes"] == ["documentation", "config", "test"]
    assert index["required_evidence"] == [
        "three_skill_workflow_item_shapes",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "focused_local_validation",
    ]
    assert index["local_validation_required"] is True
    assert index["runtime_action"] == "none"
    assert index["external_skill_activation_allowed"] is False
    assert index["external_harness_execution_allowed"] is False
    assert index["provider_runtime_launch_allowed"] is False
    assert index["remote_execution_allowed"] is False
    assert index["profile_write_allowed"] is False
    assert index["memory_write_allowed"] is False
    assert index["raw_source_url_exported"] is False
    assert index["raw_evidence_urls_exported"] is False
    assert index["raw_target_paths_exported"] is False
    assert index["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in index["rows"]}
    assert set(rows) == {
        "p1_skill_route_discovery_index",
        "p2_skill_workflow_docs",
        "p3_skill_route_metadata_config",
    }
    assert rows["p1_skill_route_discovery_index"]["proposal_kind"] == "test"
    assert rows["p1_skill_route_discovery_index"]["candidate_names"] == ["zhengxi-views"]
    assert rows["p1_skill_route_discovery_index"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert rows["p1_skill_route_discovery_index"]["selected_local_lane"] == "test"
    assert rows["p1_skill_route_discovery_index"]["selected_evidence_item_ids"] == [
        "p1_skill_route_discovery_index"
    ]
    assert "source_citation_and_advice_boundary_before_domain_skill_activation" in (
        rows["p1_skill_route_discovery_index"]["validation_gates"]
    )

    assert rows["p2_skill_workflow_docs"]["proposal_kind"] == "documentation"
    assert rows["p2_skill_workflow_docs"]["candidate_names"] == [
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert rows["p2_skill_workflow_docs"]["route_profiles"] == [
        "game_frontend_workflow",
        "source_cited_domain_research",
    ]
    assert rows["p2_skill_workflow_docs"]["selected_local_lane"] == "documentation"
    assert rows["p2_skill_workflow_docs"]["validation_target"] == (
        "document_skill_route_discovery_lane_boundary"
    )

    assert rows["p3_skill_route_metadata_config"]["proposal_kind"] == "config"
    assert rows["p3_skill_route_metadata_config"]["candidate_names"] == ["compass-skills"]
    assert rows["p3_skill_route_metadata_config"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert rows["p3_skill_route_metadata_config"]["selected_local_lane"] == "config"
    assert rows["p3_skill_route_metadata_config"]["source_metadata_signals"] == [
        "skill_registry_metadata"
    ]

    for row in rows.values():
        assert row["status"] == "ready"
        assert row["activation_blockers"] == []
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False
        assert not {"provider_runtime", "runtime_execution", "install"} & set(row["allowed_local_lanes"])

    serialized = json.dumps(index, sort_keys=True)
    assert "runtime_execution" not in serialized
    assert "install" not in serialized
    assert "https://github.com/" not in serialized

    preflight_queue = lane_map["pass3_preflight_queue"]
    assert preflight_queue["controller_surface"] == "skill_route_discovery_pass3_preflight_queue"
    assert preflight_queue["status"] == "ready"
    assert preflight_queue["decision"] == "pass3_skill_route_preflight_ready_for_final_pass_replay"
    assert preflight_queue["capability_pass"] == 3
    assert preflight_queue["total_passes"] == 4
    assert preflight_queue["operator_handoff"] == "external_supervisor_replay_before_final_pass"
    assert preflight_queue["route_index_status"] == "ready"
    assert preflight_queue["activation_handoff_status"] == "ready"
    assert preflight_queue["required_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert preflight_queue["observed_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert preflight_queue["missing_route_profiles"] == []
    assert preflight_queue["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert preflight_queue["selected_local_lanes"] == ["test", "documentation", "config"]
    assert preflight_queue["queue_blockers"] == []
    assert preflight_queue["row_count"] == 3
    assert preflight_queue["ready_row_count"] == 3
    assert preflight_queue["blocked_proposal_ids"] == []
    assert preflight_queue["required_evidence"] == [
        "pass3_route_discovery_index",
        "pass3_activation_handoff",
        "selected_item_ids_or_frozen_fixture",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert preflight_queue["runtime_action"] == "none"
    assert preflight_queue["external_skill_activation_allowed"] is False
    assert preflight_queue["external_harness_execution_allowed"] is False
    assert preflight_queue["provider_runtime_launch_allowed"] is False
    assert preflight_queue["remote_execution_allowed"] is False
    assert preflight_queue["profile_write_allowed"] is False
    assert preflight_queue["memory_write_allowed"] is False
    assert preflight_queue["raw_source_url_exported"] is False
    assert preflight_queue["raw_evidence_urls_exported"] is False
    assert preflight_queue["raw_target_paths_exported"] is False
    assert preflight_queue["raw_upstream_body_exported"] is False

    queue_rows = {row["proposal_id"]: row for row in preflight_queue["rows"]}
    assert queue_rows["p1_skill_route_discovery_index"]["candidate_names"] == ["zhengxi-views"]
    assert queue_rows["p1_skill_route_discovery_index"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert queue_rows["p1_skill_route_discovery_index"]["selected_local_lane"] == "test"
    assert queue_rows["p2_skill_workflow_docs"]["candidate_names"] == [
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert queue_rows["p2_skill_workflow_docs"]["selected_local_lane"] == "documentation"
    assert queue_rows["p3_skill_route_metadata_config"]["candidate_names"] == ["compass-skills"]
    assert queue_rows["p3_skill_route_metadata_config"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert queue_rows["p3_skill_route_metadata_config"]["selected_local_lane"] == "config"

    for row in queue_rows.values():
        assert row["status"] == "ready"
        assert row["queue_decision"] == "ready_for_final_pass_replay"
        assert row["activation_blockers"] == []
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    assert all(
        lane["proposal_kind"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        for lane in lane_map["proposal_lanes"]
    )
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["external_skill_activation_allowed"] is False for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_pass3_local_validation_lane_probes_current_skill_workflows():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass3_local_validation_lane.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry(payload["candidates"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["downgraded_candidate_count"] == 3
    assert lane_map["rejected_candidate_count"] == 0

    lane = lane_map["pass3_local_validation_lane"]
    assert lane["controller_surface"] == "skill_route_discovery_pass3_local_validation_lane"
    assert lane["source_digest"] == "github-growth-20260627T194729.481658Z"
    assert lane["status"] == "ready"
    assert lane["decision"] == "pass3_skill_route_local_lanes_ready_for_validation"
    assert lane["capability_pass"] == 3
    assert lane["total_passes"] == 4
    assert lane["review_gate"] == "focused-evidence-review"
    assert lane["operator_handoff"] == "external_supervisor_replay_before_final_pass"
    assert lane["proposal_count"] == 3
    assert lane["ready_proposal_count"] == 3
    assert lane["blocked_proposal_ids"] == []
    assert lane["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert lane["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane["selected_local_lanes"] == ["documentation", "config", "test"]
    assert lane["downgraded_lane_names"] == [
        "install",
        "provider_runtime",
        "runtime_execution",
    ]
    assert any("missing_detail_risk" in note for note in lane["uncertainty_notes"])
    assert lane["required_evidence"] == [
        "three_skill_workflow_item_shapes",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    replay_contract = lane["operator_replay_contract"]
    assert replay_contract["controller_surface"] == "skill_route_discovery_pass3_operator_replay_contract"
    assert replay_contract["status"] == "ready"
    assert replay_contract["decision"] == "supervisor_can_replay_pass3_skill_lanes_before_final_pass"
    assert replay_contract["proposal_ids"] == [
        "p1-skill-route-discovery-index",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert replay_contract["blocked_proposal_ids"] == []
    assert replay_contract["row_count"] == 3
    assert replay_contract["ready_row_count"] == 3
    assert replay_contract["selected_local_lanes"] == ["test", "documentation", "config"]
    assert all(command_hash.startswith("sha256:") for command_hash in replay_contract["replay_command_hashes"])
    assert replay_contract["rollback_artifact_required"] is True
    assert replay_contract["rollback_ref_required"] is True
    assert replay_contract["operator_next_action"] == "run_replay_commands_then_continue_to_final_pass"
    assert replay_contract["runtime_action"] == "none"
    assert replay_contract["external_skill_activation_allowed"] is False
    assert replay_contract["external_harness_execution_allowed"] is False
    assert replay_contract["provider_runtime_launch_allowed"] is False
    assert replay_contract["remote_execution_allowed"] is False
    assert replay_contract["raw_replay_commands_exported"] is False
    assert replay_contract["raw_source_url_exported"] is False
    assert replay_contract["raw_evidence_urls_exported"] is False
    assert replay_contract["raw_target_paths_exported"] is False
    assert replay_contract["raw_upstream_body_exported"] is False
    assert lane["local_validation_required"] is True
    assert lane["runtime_action"] == "none"
    assert lane["external_skill_activation_allowed"] is False
    assert lane["external_harness_execution_allowed"] is False
    assert lane["provider_runtime_launch_allowed"] is False
    assert lane["remote_execution_allowed"] is False
    assert lane["profile_write_allowed"] is False
    assert lane["memory_write_allowed"] is False
    assert lane["raw_source_url_exported"] is False
    assert lane["raw_evidence_urls_exported"] is False
    assert lane["raw_target_paths_exported"] is False
    assert lane["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in lane["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-index",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-state-handoff",
    }
    assert rows["p1-skill-route-discovery-index"]["candidate_names"] == ["zhengxi-views"]
    assert rows["p1-skill-route-discovery-index"]["route_profiles"] == ["generic_skill_workflow"]
    assert rows["p1-skill-route-discovery-index"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-index"]["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-index"
    ]

    assert rows["p2-game-frontend-skill-profile"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["p2-game-frontend-skill-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p2-game-frontend-skill-profile"]["selected_local_lane"] == "documentation"
    assert rows["p2-game-frontend-skill-profile"]["validation_target"] == (
        "document_game_frontend_workflow_without_expanding_lanes"
    )

    assert rows["p3-skill-ecosystem-state-handoff"]["candidate_names"] == ["compass-skills"]
    assert rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "config"
    assert rows["p3-skill-ecosystem-state-handoff"]["validation_target"] == (
        "state_handoff_metadata_stays_local_and_body_free"
    )

    for row in rows.values():
        assert row["status"] == "ready"
        assert row["activation_blockers"] == []
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        bounded_contract = row["bounded_lane_contract"]
        assert bounded_contract["controller_surface"] == "skill_route_discovery_pass3_bounded_lane_contract"
        assert bounded_contract["selected_lane_bounded"] is True
        assert bounded_contract["allowed_lane_count"] == len(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert set(bounded_contract["unsupported_lanes_removed"]) <= {
            "install",
            "provider_runtime",
            "runtime_execution",
        }
        assert bounded_contract["activation_gate"] == "local_validation_before_activation"
        assert bounded_contract["local_validation_required"] is True
        assert bounded_contract["runtime_action"] == "none"
        assert bounded_contract["external_skill_activation_allowed"] is False
        assert bounded_contract["external_harness_execution_allowed"] is False
        assert bounded_contract["provider_runtime_launch_allowed"] is False
        assert bounded_contract["remote_execution_allowed"] is False
        assert bounded_contract["raw_source_url_exported"] is False
        assert bounded_contract["raw_evidence_urls_exported"] is False
        assert bounded_contract["raw_target_paths_exported"] is False
        assert bounded_contract["raw_upstream_body_exported"] is False
        assert row["candidate_source_hashes"][0].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False
        assert not {"provider_runtime", "runtime_execution", "install"} & set(row["allowed_local_lanes"])

    serialized_lane = json.dumps(lane, sort_keys=True)
    assert "https://github.com/" not in serialized_lane


def test_skill_route_discovery_pass3_current_wake_acceptance_packet_keeps_agent_eval_adjacent():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_wake_pass3_acceptance_packet.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["ignored_evidence_item_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0

    packet = lane_map["pass3_current_wake_acceptance_packet"]
    assert packet["controller_surface"] == "skill_route_discovery_pass3_current_wake_acceptance_packet"
    assert packet["status"] == "ready"
    assert packet["decision"] == "current_wake_pass3_lanes_ready_for_supervisor_acceptance"
    assert packet["source_digest"] == "github-growth-20260627T210729.503389Z"
    assert packet["capability_pass"] == 3
    assert packet["total_passes"] == 4
    assert packet["review_gate"] == "focused-evidence-review"
    assert packet["proposal_ids"] == [
        "p1-skill-route-discovery-index",
        "p2-skill-route-discovery-docs",
        "p3-agent-harness-eval-fixtures",
    ]
    assert packet["ready_proposal_count"] == 3
    assert packet["blocked_proposal_ids"] == []
    assert packet["skill_route_candidate_count"] == 3
    assert packet["adjacent_general_agent_count"] == 1
    assert packet["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert packet["missing_route_profiles"] == []
    assert packet["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert packet["selected_local_lanes"] == ["test", "documentation"]
    assert packet["adjacent_evaluation_lane"] == "agent_harness_eval_required"
    assert packet["unsupported_lane_names_removed"] == []
    assert packet["required_evidence"] == [
        "three_skill_workflow_item_shapes",
        "adjacent_general_agent_item_without_skill_workflow_signal",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert packet["local_validation_required"] is True
    assert packet["runtime_action"] == "none"
    assert packet["external_skill_activation_allowed"] is False
    assert packet["external_agent_activation_allowed"] is False
    assert packet["external_harness_execution_allowed"] is False
    assert packet["provider_runtime_launch_allowed"] is False
    assert packet["remote_execution_allowed"] is False
    assert packet["profile_write_allowed"] is False
    assert packet["memory_write_allowed"] is False
    assert packet["raw_replay_commands_exported"] is False
    assert packet["raw_source_url_exported"] is False
    assert packet["raw_evidence_urls_exported"] is False
    assert packet["raw_target_paths_exported"] is False
    assert packet["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in packet["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-index",
        "p2-skill-route-discovery-docs",
        "p3-agent-harness-eval-fixtures",
    }
    assert rows["p1-skill-route-discovery-index"]["proposal_kind"] == "test"
    assert rows["p1-skill-route-discovery-index"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-index"]["candidate_names"] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert rows["p1-skill-route-discovery-index"]["status"] == "ready"
    assert rows["p1-skill-route-discovery-index"]["activation_blockers"] == []

    assert rows["p2-skill-route-discovery-docs"]["proposal_kind"] == "documentation"
    assert rows["p2-skill-route-discovery-docs"]["selected_local_lane"] == "documentation"
    assert rows["p2-skill-route-discovery-docs"]["status"] == "ready"
    assert rows["p2-skill-route-discovery-docs"]["activation_blockers"] == []

    agent_eval = rows["p3-agent-harness-eval-fixtures"]
    assert agent_eval["proposal_kind"] == "test"
    assert agent_eval["selected_local_lane"] == "agent_harness_eval_required"
    assert agent_eval["candidate_names"] == ["Qwen-AgentWorld"]
    assert agent_eval["route_profiles"] == []
    assert agent_eval["selected_evidence_item_ids"] == ["p3-agent-harness-eval-qwen-agentworld"]
    assert agent_eval["validation_gates"] == [
        "local_agent_harness_eval_required_before_implementation_route"
    ]
    assert agent_eval["status"] == "ready"
    assert agent_eval["activation_blockers"] == []
    assert agent_eval["external_agent_activation_allowed"] is False
    assert agent_eval["external_harness_execution_allowed"] is False
    assert agent_eval["remote_execution_allowed"] is False

    for row in packet["skill_route_rows"]:
        assert row["row_status"] == "ready"
        assert row["route_hint"] == SKILL_ROUTE_DISCOVERY_HINT
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False

    adjacent = packet["adjacent_general_agent_rows"][0]
    assert adjacent["proposal_id"] == "p3-agent-harness-eval-fixtures"
    assert adjacent["item_id"] == "p3-agent-harness-eval-qwen-agentworld"
    assert adjacent["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent["skill_route_discovery_inherited"] is False
    assert adjacent["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert adjacent["direct_runtime_route_allowed"] is False
    assert adjacent["direct_code_patch_route_allowed"] is False
    assert adjacent["replay_command_hash"].startswith("sha256:")
    assert adjacent["raw_replay_command_exported"] is False
    assert "replay_command" not in adjacent
    assert adjacent["local_validation_required"] is True
    assert adjacent["runtime_action"] == "none"
    assert adjacent["external_agent_activation_allowed"] is False
    assert adjacent["external_harness_execution_allowed"] is False
    assert adjacent["provider_runtime_launch_allowed"] is False
    assert adjacent["remote_execution_allowed"] is False

    serialized = json.dumps(packet, sort_keys=True)
    assert "https://github.com/" not in serialized
    assert "python -m pytest" not in serialized


def test_skill_route_discovery_pass3_active_window_review_packet_matches_current_proposals():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass3_active_review_packet.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["ignored_evidence_item_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0

    packet = lane_map["pass3_active_window_review_packet"]
    assert packet["controller_surface"] == "skill_route_discovery_pass3_active_window_review_packet"
    assert packet["status"] == "ready"
    assert packet["decision"] == "active_window_pass3_routes_ready_for_supervisor_review"
    assert packet["source_digest"] == "github-growth-20260627T222729.506372Z"
    assert packet["capability_pass"] == 3
    assert packet["total_passes"] == 4
    assert packet["review_gate"] == "focused-evidence-review"
    assert packet["proposal_ids"] == [
        "p1-skill-route-discovery-matrix",
        "p2-skill-route-documentation",
        "p3-agent-harness-eval-fixtures",
    ]
    assert packet["ready_proposal_count"] == 3
    assert packet["blocked_proposal_ids"] == []
    assert packet["skill_route_candidate_count"] == 3
    assert packet["adjacent_general_agent_count"] == 1
    assert packet["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert packet["missing_route_profiles"] == []
    assert packet["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert packet["selected_local_lanes"] == ["test", "documentation"]
    assert packet["adjacent_evaluation_lane"] == "agent_harness_eval_required"
    assert packet["unsupported_lane_names_removed"] == []
    assert packet["required_evidence"] == [
        "generic_game_and_ecosystem_skill_workflow_shapes",
        "adjacent_general_agent_item_without_skill_workflow_signal",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert packet["operator_next_action"] == "run_hashed_replay_commands_then_continue_to_pass4"
    assert packet["local_validation_required"] is True
    assert packet["runtime_action"] == "none"
    assert packet["external_skill_activation_allowed"] is False
    assert packet["external_agent_activation_allowed"] is False
    assert packet["external_harness_execution_allowed"] is False
    assert packet["provider_runtime_launch_allowed"] is False
    assert packet["remote_execution_allowed"] is False
    assert packet["profile_write_allowed"] is False
    assert packet["memory_write_allowed"] is False
    assert packet["raw_replay_commands_exported"] is False
    assert packet["raw_source_url_exported"] is False
    assert packet["raw_evidence_urls_exported"] is False
    assert packet["raw_target_paths_exported"] is False
    assert packet["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in packet["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-matrix",
        "p2-skill-route-documentation",
        "p3-agent-harness-eval-fixtures",
    }
    assert rows["p1-skill-route-discovery-matrix"]["proposal_kind"] == "test"
    assert rows["p1-skill-route-discovery-matrix"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-matrix"]["candidate_names"] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert rows["p1-skill-route-discovery-matrix"]["status"] == "ready"
    assert rows["p1-skill-route-discovery-matrix"]["activation_blockers"] == []

    assert rows["p2-skill-route-documentation"]["proposal_kind"] == "documentation"
    assert rows["p2-skill-route-documentation"]["selected_local_lane"] == "documentation"
    assert rows["p2-skill-route-documentation"]["status"] == "ready"
    assert rows["p2-skill-route-documentation"]["activation_blockers"] == []

    agent_eval = rows["p3-agent-harness-eval-fixtures"]
    assert agent_eval["proposal_kind"] == "test"
    assert agent_eval["selected_local_lane"] == "agent_harness_eval_required"
    assert agent_eval["candidate_names"] == ["Qwen-AgentWorld"]
    assert agent_eval["route_profiles"] == []
    assert agent_eval["selected_evidence_item_ids"] == ["p3-agent-harness-eval-qwen-agentworld"]
    assert agent_eval["validation_gates"] == [
        "local_agent_harness_eval_required_before_implementation_route"
    ]
    assert agent_eval["status"] == "ready"
    assert agent_eval["activation_blockers"] == []
    assert agent_eval["external_agent_activation_allowed"] is False
    assert agent_eval["external_harness_execution_allowed"] is False
    assert agent_eval["remote_execution_allowed"] is False

    skill_rows = {row["candidate_name"]: row for row in packet["skill_route_rows"]}
    assert skill_rows["zhengxi-views"]["route_profiles"] == ["generic_skill_workflow"]
    assert skill_rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert skill_rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    for row in skill_rows.values():
        assert row["row_status"] == "ready"
        assert row["classification_decision"] == "skill_route_discovery_first"
        assert row["route_hint"] == SKILL_ROUTE_DISCOVERY_HINT
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False

    adjacent = packet["adjacent_general_agent_rows"][0]
    assert adjacent["proposal_id"] == "p3-agent-harness-eval-fixtures"
    assert adjacent["item_id"] == "p3-agent-harness-eval-qwen-agentworld"
    assert adjacent["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent["skill_route_discovery_inherited"] is False
    assert adjacent["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert adjacent["direct_runtime_route_allowed"] is False
    assert adjacent["direct_code_patch_route_allowed"] is False
    assert adjacent["replay_command_hash"].startswith("sha256:")
    assert adjacent["raw_replay_command_exported"] is False
    assert "replay_command" not in adjacent
    assert adjacent["local_validation_required"] is True
    assert adjacent["runtime_action"] == "none"
    assert adjacent["external_agent_activation_allowed"] is False
    assert adjacent["external_harness_execution_allowed"] is False
    assert adjacent["provider_runtime_launch_allowed"] is False
    assert adjacent["remote_execution_allowed"] is False

    serialized = json.dumps(packet, sort_keys=True)
    assert "https://github.com/" not in serialized
    assert "python -m pytest" not in serialized


def test_skill_route_discovery_pass3_active_proposal_acceptance_lane_matches_current_window():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass3_active_proposal_acceptance.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 3
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    lane = lane_map["pass3_active_proposal_acceptance_lane"]
    assert lane["controller_surface"] == "skill_route_discovery_pass3_active_proposal_acceptance_lane"
    assert lane["status"] == "ready"
    assert lane["decision"] == "active_pass3_skill_route_proposals_ready_for_local_acceptance"
    assert lane["source_digest"] == "github-growth-20260627T234729.527065Z"
    assert lane["capability_pass"] == 3
    assert lane["total_passes"] == 4
    assert lane["review_gate"] == "focused-evidence-review"
    assert lane["proposal_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-workflow",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert lane["ready_proposal_count"] == 3
    assert lane["blocked_proposal_ids"] == []
    assert lane["required_route_profiles"] == [
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert lane["observed_route_profiles"] == [
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert lane["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert lane["selected_local_lanes"] == ["documentation", "config", "test"]
    assert lane["unsupported_lane_names_removed"] == []
    assert lane["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert lane["operator_next_action"] == "run_hashed_replay_commands_then_continue_to_pass4"
    assert lane["local_validation_required"] is True
    assert lane["runtime_action"] == "none"
    assert lane["external_skill_activation_allowed"] is False
    assert lane["external_harness_execution_allowed"] is False
    assert lane["provider_runtime_launch_allowed"] is False
    assert lane["remote_execution_allowed"] is False
    assert lane["profile_write_allowed"] is False
    assert lane["memory_write_allowed"] is False
    assert lane["raw_replay_commands_exported"] is False
    assert lane["raw_source_url_exported"] is False
    assert lane["raw_evidence_urls_exported"] is False
    assert lane["raw_target_paths_exported"] is False
    assert lane["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in lane["rows"]}
    assert set(rows) == {"compass-skills", "threejs-game-skills", "zhengxi-views"}
    assert rows["zhengxi-views"]["proposal_id"] == "p1-skill-route-discovery-generic"
    assert rows["zhengxi-views"]["proposal_kind"] == "test"
    assert rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert rows["zhengxi-views"]["route_profile"] == "generic_skill_workflow"
    assert rows["threejs-game-skills"]["proposal_id"] == "p2-game-frontend-skill-workflow"
    assert rows["threejs-game-skills"]["proposal_kind"] == "documentation"
    assert rows["threejs-game-skills"]["selected_local_lane"] == "documentation"
    assert rows["threejs-game-skills"]["route_profile"] == "game_frontend_workflow"
    assert rows["compass-skills"]["proposal_id"] == "p3-skill-ecosystem-state-handoff"
    assert rows["compass-skills"]["proposal_kind"] == "config"
    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["compass-skills"]["route_profile"] == "skill_ecosystem_state_handoff"

    for row in rows.values():
        assert row["row_status"] == "ready"
        assert row["route_hint"] == SKILL_ROUTE_DISCOVERY_HINT
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert not {"provider_runtime", "runtime_execution", "install"} & set(row["allowed_local_lanes"])
        assert row["selected_evidence_item_ids"]
        assert row["activation_blockers"] == []
        assert row["replay_command_hash"].startswith("sha256:")
        assert row["raw_replay_command_exported"] is False
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    serialized = json.dumps(lane, sort_keys=True)
    assert "https://github.com/" not in serialized
    assert "python -m pytest" not in serialized


def test_skill_route_discovery_current_pass2_focused_evidence_review_is_bounded():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_pass2_focused_evidence_review.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 3
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0
    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0

    review = lane_map["focused_evidence_review_lane"]
    assert review["controller_surface"] == "skill_route_discovery_focused_evidence_review_lane"
    assert review["status"] == "ready"
    assert review["decision"] == "active_skill_route_proposals_ready_for_bounded_local_validation"
    assert review["review_gate"] == "focused-evidence-review"
    assert review["proposal_count"] == 3
    assert review["ready_proposal_count"] == 3
    assert review["blocked_proposal_ids"] == []
    assert review["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert review["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert review["runtime_action"] == "none"
    assert review["external_skill_activation_allowed"] is False
    assert review["external_harness_execution_allowed"] is False
    assert review["provider_runtime_launch_allowed"] is False
    assert review["remote_execution_allowed"] is False
    assert review["raw_source_url_exported"] is False
    assert review["raw_evidence_urls_exported"] is False
    assert review["raw_target_paths_exported"] is False
    assert review["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in review["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-baseline",
        "p2-skill-ecosystem-documentation",
        "p3-game-frontend-skill-validation",
    }
    assert rows["p1-skill-route-discovery-baseline"]["proposal_kind"] == "test"
    assert rows["p1-skill-route-discovery-baseline"]["candidate_names"] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert rows["p1-skill-route-discovery-baseline"]["route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert rows["p1-skill-route-discovery-baseline"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-baseline"]["validation_target"] == (
        "skill_workflow_lanes_stay_bounded"
    )

    assert rows["p2-skill-ecosystem-documentation"]["proposal_kind"] == "documentation"
    assert rows["p2-skill-ecosystem-documentation"]["selected_local_lane"] == "documentation"
    assert rows["p2-skill-ecosystem-documentation"]["validation_target"] == (
        "document_allowed_lanes_and_uncertainty_limits"
    )

    assert rows["p3-game-frontend-skill-validation"]["proposal_kind"] == "code_patch"
    assert rows["p3-game-frontend-skill-validation"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["p3-game-frontend-skill-validation"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p3-game-frontend-skill-validation"]["selected_local_lane"] == "test"
    assert rows["p3-game-frontend-skill-validation"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert rows["p3-game-frontend-skill-validation"]["validation_target"] == (
        "local_frontend_render_or_workflow_check"
    )
    assert rows["p3-game-frontend-skill-validation"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend"
    )

    for row in rows.values():
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert all(item_id.startswith(("p1-", "p2-", "p3-")) for item_id in row["selected_evidence_item_ids"])
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False


def test_skill_route_discovery_current_window_pass2_focused_review_maps_active_proposals():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass2_focused_review.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 3
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    review = lane_map["current_window_pass2_focused_review"]
    assert review["controller_surface"] == "skill_route_discovery_current_window_pass2_focused_review"
    assert review["status"] == "ready"
    assert review["decision"] == "current_window_pass2_skill_routes_ready_for_focused_local_validation"
    assert review["source_digest"] == "unknown"
    assert review["capability_pass"] == 2
    assert review["total_passes"] == 4
    assert review["review_gate"] == "focused-evidence-review"
    assert review["proposal_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-skill-route-discovery-game-frontend-profile",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert review["proposal_count"] == 3
    assert review["ready_proposal_count"] == 3
    assert review["blocked_proposal_ids"] == []
    assert review["observed_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert review["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert review["selected_local_lanes"] == ["documentation", "test"]
    assert review["required_evidence"] == [
        "selected_digest_item_ids_or_frozen_digest_evidence",
        "body_free_repository_summary",
        "hashed_evidence_urls",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert review["runtime_action"] == "none"
    assert review["external_skill_activation_allowed"] is False
    assert review["external_agent_activation_allowed"] is False
    assert review["external_harness_execution_allowed"] is False
    assert review["provider_runtime_launch_allowed"] is False
    assert review["profile_write_allowed"] is False
    assert review["memory_write_allowed"] is False
    assert review["remote_execution_allowed"] is False
    assert review["raw_source_url_exported"] is False
    assert review["raw_evidence_urls_exported"] is False
    assert review["raw_target_paths_exported"] is False
    assert review["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in review["rows"]}
    assert rows["p1-skill-route-discovery-generic"]["proposal_kind"] == "test"
    assert rows["p1-skill-route-discovery-generic"]["candidate_names"] == ["zhengxi-views"]
    assert rows["p1-skill-route-discovery-generic"]["route_profiles"] == ["source_cited_domain_research"]
    assert rows["p1-skill-route-discovery-generic"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-generic"]["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-generic"
    ]

    assert rows["p2-skill-route-discovery-game-frontend-profile"]["proposal_kind"] == "documentation"
    assert rows["p2-skill-route-discovery-game-frontend-profile"]["candidate_names"] == [
        "threejs-game-skills"
    ]
    assert rows["p2-skill-route-discovery-game-frontend-profile"]["route_profiles"] == [
        "game_frontend_workflow"
    ]
    assert rows["p2-skill-route-discovery-game-frontend-profile"]["selected_local_lane"] == "documentation"

    assert rows["p3-skill-ecosystem-state-handoff"]["proposal_kind"] == "test"
    assert rows["p3-skill-ecosystem-state-handoff"]["candidate_names"] == ["compass-skills"]
    assert rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "test"
    assert rows["p3-skill-ecosystem-state-handoff"]["profile_write_allowed"] is False
    assert rows["p3-skill-ecosystem-state-handoff"]["memory_write_allowed"] is False

    for row in rows.values():
        assert row["status"] == "ready"
        assert row["activation_blockers"] == []
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"]
        assert row["evidence_url_hashes"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert all(evidence_hash.startswith("sha256:") for evidence_hash in row["evidence_url_hashes"])
        assert row["validation_gate"] == "focused-evidence-review"
        assert row["replay_command"] == (
            "python -m pytest tests/test_skill_routing.py -q -k current_window_pass2_focused_review"
        )
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    serialized = json.dumps(review, sort_keys=True)
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_current_pass2_validation_lane_keeps_agent_eval_adjacent():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_pass2_skill_and_agent_validation_lane.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 3
    assert registry["candidate_count"] == 2
    assert registry["ignored_evidence_item_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0

    ignored = registry["ignored_evidence_items"][0]
    assert ignored["item_id"] == "p2-agent-harness-eval-qwen-agentworld"
    assert ignored["evaluation_lane"] == "agent_harness_eval_required"
    assert ignored["skill_route_discovery_inherited"] is False
    assert ignored["direct_runtime_route_allowed"] is False
    assert ignored["direct_code_patch_route_allowed"] is False

    current = lane_map["current_pass2_validation_lane"]
    assert current["controller_surface"] == "skill_route_discovery_current_pass2_validation_lane"
    assert current["status"] == "ready"
    assert current["decision"] == "current_pass2_skill_and_agent_evidence_ready_for_local_validation"
    assert current["source_digest"] == "github-growth-20260627T192729.517144Z"
    assert current["proposal_ids"] == [
        "p1-skill-route-discovery-general",
        "p2-agent-harness-eval",
        "p3-game-frontend-skill-profile",
    ]
    assert current["skill_route_candidate_count"] == 2
    assert current["adjacent_general_agent_count"] == 1
    assert current["agent_harness_eval_required"] is True
    assert current["agent_harness_required_signals"] == [
        "install_shape",
        "entrypoints",
        "dependency_boundaries",
        "task_loop_assumptions",
        "observable_behaviors",
        "evaluation_dimensions",
    ]
    assert current["agent_harness_evaluation_dimensions"] == [
        "format",
        "factuality",
        "consistency",
        "realism",
        "quality",
    ]
    assert current["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert set(current["selected_local_lanes"]) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert current["runtime_action"] == "none"
    assert current["external_skill_activation_allowed"] is False
    assert current["external_agent_activation_allowed"] is False
    assert current["external_harness_execution_allowed"] is False
    assert current["provider_runtime_launch_allowed"] is False
    assert current["remote_execution_allowed"] is False
    assert current["raw_source_url_exported"] is False
    assert current["raw_evidence_urls_exported"] is False
    assert current["raw_target_paths_exported"] is False
    assert current["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in current["rows"]}
    assert rows["p1-skill-route-discovery-general"]["candidate_name"] == "zhengxi-views"
    assert rows["p1-skill-route-discovery-general"]["route_profiles"] == ["generic_skill_workflow"]
    assert rows["p1-skill-route-discovery-general"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert rows["p1-skill-route-discovery-general"]["selected_local_lane"] == "documentation"
    assert rows["p1-skill-route-discovery-general"]["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-general"
    ]
    assert rows["p1-skill-route-discovery-general"]["row_status"] == "ready"

    assert rows["p3-game-frontend-skill-profile"]["candidate_name"] == "threejs-game-skills"
    assert rows["p3-game-frontend-skill-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p3-game-frontend-skill-profile"]["selected_local_lane"] == "test"
    assert rows["p3-game-frontend-skill-profile"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert rows["p3-game-frontend-skill-profile"]["replay_command"] == (
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend"
    )

    adjacent = current["adjacent_general_agent_rows"][0]
    assert adjacent["proposal_id"] == "p2-agent-harness-eval"
    assert adjacent["item_id"] == "p2-agent-harness-eval-qwen-agentworld"
    assert adjacent["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent["skill_route_discovery_inherited"] is False
    assert adjacent["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert adjacent["direct_runtime_route_allowed"] is False
    assert adjacent["direct_code_patch_route_allowed"] is False
    assert adjacent["replay_command"] == "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
    assert adjacent["external_agent_activation_allowed"] is False
    assert adjacent["external_harness_execution_allowed"] is False
    assert adjacent["provider_runtime_launch_allowed"] is False
    assert adjacent["remote_execution_allowed"] is False

    serialized = json.dumps(current, sort_keys=True)
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_active_pass1_fixtures_queue_general_agent_evidence():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass1_skill_route_fixtures.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["ignored_evidence_item_count"] == 1
    ignored = registry["ignored_evidence_items"][0]
    assert ignored["item_id"] == "p3-qwen-agentworld-general-agent"
    assert ignored["name"] == "Qwen-AgentWorld"
    assert ignored["source_hash"] == "sha256:cdcbe295942e4731725256fdb6df0739a9a86b2273f081c26be11d7aed78653c"
    assert ignored["ignored_reason"] == "no_skill_workflow_signal"
    assert ignored["evaluation_lane"] == "agent_harness_eval_required"
    assert ignored["skill_route_discovery_inherited"] is False
    assert ignored["direct_runtime_route_allowed"] is False
    assert ignored["direct_code_patch_route_allowed"] is False

    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0

    active_lane = lane_map["active_pass1_evidence_lane"]
    assert active_lane["controller_surface"] == "skill_route_discovery_active_pass1_evidence_lane"
    assert active_lane["status"] == "ready"
    assert active_lane["decision"] == "active_pass1_skill_route_evidence_ready_for_local_validation"
    assert active_lane["source_digest"] == "github-growth-20260627T142310.634775Z"
    assert active_lane["proposal_ids"] == [
        "p1-skill-route-discovery-fixtures",
        "p2-game-frontend-skill-profile",
        "p3-agent-harness-eval-for-general-agent-projects",
    ]
    assert active_lane["covered_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert active_lane["missing_route_profiles"] == []
    assert active_lane["accepted_skill_route_count"] == 3
    assert active_lane["adjacent_general_agent_count"] == 1
    assert active_lane["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert active_lane["selected_local_lanes"] == ["config", "test"]
    assert active_lane["local_validation_required"] is True
    assert active_lane["runtime_action"] == "none"
    assert active_lane["external_skill_activation_allowed"] is False
    assert active_lane["external_agent_activation_allowed"] is False
    assert active_lane["external_harness_execution_allowed"] is False
    assert active_lane["provider_runtime_launch_allowed"] is False
    assert active_lane["remote_execution_allowed"] is False
    assert active_lane["raw_source_url_exported"] is False
    assert active_lane["raw_evidence_urls_exported"] is False
    assert active_lane["raw_target_paths_exported"] is False
    assert active_lane["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in active_lane["rows"]}
    assert rows["compass-skills"]["proposal_id"] == "p1-skill-route-discovery-fixtures"
    assert rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["threejs-game-skills"]["proposal_id"] == "p2-game-frontend-skill-profile"
    assert rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert rows["zhengxi-views"]["proposal_id"] == "p1-skill-route-discovery-fixtures"
    assert rows["zhengxi-views"]["route_profiles"] == ["source_cited_domain_research"]
    assert rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert all(set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES) for row in rows.values())
    assert all(row["local_validation_required"] is True for row in rows.values())
    assert all(row["runtime_action"] == "none" for row in rows.values())
    assert all(row["external_skill_activation_allowed"] is False for row in rows.values())
    assert all(row["external_harness_execution_allowed"] is False for row in rows.values())

    adjacent_row = active_lane["adjacent_general_agent_rows"][0]
    assert adjacent_row["proposal_id"] == "p3-agent-harness-eval-for-general-agent-projects"
    assert adjacent_row["item_id"] == "p3-qwen-agentworld-general-agent"
    assert adjacent_row["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent_row["skill_route_discovery_inherited"] is False
    assert adjacent_row["allowed_local_lanes"] == []
    assert adjacent_row["direct_runtime_route_allowed"] is False
    assert adjacent_row["direct_code_patch_route_allowed"] is False
    assert adjacent_row["required_before_implementation"] == "local_agent_harness_eval_route_established"
    assert adjacent_row["local_validation_required"] is True
    assert adjacent_row["runtime_action"] == "none"
    assert adjacent_row["external_agent_activation_allowed"] is False
    assert adjacent_row["external_harness_execution_allowed"] is False
    assert adjacent_row["provider_runtime_launch_allowed"] is False
    assert adjacent_row["remote_execution_allowed"] is False

    active_window = lane_map["active_window_pass1_route_lanes"]
    assert active_window["controller_surface"] == "skill_route_discovery_active_window_pass1_route_lanes"
    assert active_window["status"] == "ready"
    assert active_window["decision"] == "active_window_pass1_skill_route_lanes_ready_for_local_validation"
    assert active_window["source_digest"] == "github-growth-20260627T190729.505995Z"
    assert active_window["review_gate"] == "focused-evidence-review"
    assert active_window["proposal_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert active_window["blocked_proposal_ids"] == []
    assert active_window["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert active_window["selected_local_lanes"] == ["documentation", "config", "test"]

    assert active_window["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert active_window["runtime_action"] == "none"
    assert active_window["external_skill_activation_allowed"] is False
    assert active_window["external_agent_activation_allowed"] is False
    assert active_window["external_harness_execution_allowed"] is False
    assert active_window["provider_runtime_launch_allowed"] is False
    assert active_window["profile_write_allowed"] is False
    assert active_window["memory_write_allowed"] is False
    assert active_window["remote_execution_allowed"] is False
    assert active_window["raw_source_url_exported"] is False
    assert active_window["raw_evidence_urls_exported"] is False
    assert active_window["raw_target_paths_exported"] is False
    assert active_window["raw_upstream_body_exported"] is False

    window_rows = {row["proposal_id"]: row for row in active_window["rows"]}
    assert set(window_rows) == {
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-state-handoff",
    }
    assert window_rows["p1-skill-route-discovery-generic"]["candidate_names"] == ["zhengxi-views"]
    assert window_rows["p1-skill-route-discovery-generic"]["route_profiles"] == [
        "source_cited_domain_research"
    ]
    assert window_rows["p1-skill-route-discovery-generic"]["proposal_kind"] == "test"
    assert window_rows["p1-skill-route-discovery-generic"]["selected_local_lane"] == "test"
    assert window_rows["p2-game-frontend-skill-profile"]["candidate_names"] == [
        "threejs-game-skills"
    ]
    assert window_rows["p2-game-frontend-skill-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert window_rows["p2-game-frontend-skill-profile"]["proposal_kind"] == "documentation"
    assert window_rows["p2-game-frontend-skill-profile"]["selected_local_lane"] == "documentation"
    assert window_rows["p2-game-frontend-skill-profile"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert window_rows["p3-skill-ecosystem-state-handoff"]["candidate_names"] == ["compass-skills"]
    assert window_rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert window_rows["p3-skill-ecosystem-state-handoff"]["proposal_kind"] == "config"
    assert window_rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "config"
    assert window_rows["p3-skill-ecosystem-state-handoff"]["profile_write_allowed"] is False
    assert window_rows["p3-skill-ecosystem-state-handoff"]["memory_write_allowed"] is False

    for row in active_window["rows"]:
        assert row["status"] == "ready"
        assert row["route_hint"] == "skill_route_discovery"
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["selected_evidence_item_ids"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert row["code_patch_approval_gate"] == "selected_lane_local_validation_before_code_patch"
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    active_window_adjacent = active_window["adjacent_general_agent_rows"][0]
    assert active_window_adjacent["item_id"] == "p3-qwen-agentworld-general-agent"
    assert active_window_adjacent["evaluation_lane"] == "agent_harness_eval_required"
    assert active_window_adjacent["skill_route_discovery_inherited"] is False
    assert active_window_adjacent["direct_runtime_route_allowed"] is False
    assert active_window_adjacent["direct_code_patch_route_allowed"] is False


def test_skill_route_discovery_active_pass1_lane_uses_current_source_digest():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_digest_pass1_skill_route_fixtures.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["source_digest"] == "github-growth-20260627T202729.517326Z"
    active_lane = lane_map["active_pass1_evidence_lane"]
    assert active_lane["status"] == "ready"
    assert active_lane["source_digest"] == payload["source_digest"]
    assert active_lane["accepted_skill_route_count"] == 3
    assert active_lane["adjacent_general_agent_count"] == 1
    assert active_lane["covered_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert active_lane["selected_local_lanes"] == ["config", "test"]

    adjacent_row = active_lane["adjacent_general_agent_rows"][0]
    assert adjacent_row["item_id"] == "p3-current-qwen-agentworld-general-agent"
    assert adjacent_row["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent_row["skill_route_discovery_inherited"] is False
    assert adjacent_row["direct_runtime_route_allowed"] is False
    assert adjacent_row["direct_code_patch_route_allowed"] is False
    assert adjacent_row["external_harness_execution_allowed"] is False

    serialized = json.dumps(active_lane, sort_keys=True)
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_current_pass1_route_discovery_index_matches_active_proposals():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_pass1_route_discovery_index.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["source_digest"] == "github-growth-20260628T002729.501775Z"
    assert registry["candidate_count"] == 3
    assert registry["ignored_evidence_item_count"] == 1
    assert lane_map["proposal_lane_count"] == 12

    index = lane_map["current_pass1_route_discovery_index"]
    assert index["controller_surface"] == "skill_route_discovery_current_pass1_route_discovery_index"
    assert index["status"] == "ready"
    assert index["decision"] == "current_pass1_skill_route_index_ready_for_bounded_local_validation"
    assert index["source_digest"] == payload["source_digest"]
    assert index["capability_pass"] == 1
    assert index["total_passes"] == 4
    assert index["review_gate"] == "focused-evidence-review"
    assert index["proposal_ids"] == [
        "p1-skill-route-discovery-index",
        "p2-skill-route-discovery-test-fixtures",
        "p3-game-frontend-skill-profile",
        "p4-skill-ecosystem-state-handoff-profile",
        "p5-agent-project-harness-eval-doc",
    ]
    assert index["blocked_proposal_ids"] == []
    assert index["observed_route_profiles"] == [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert index["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert index["selected_local_lanes"] == ["documentation", "config", "test"]
    assert index["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert index["runtime_action"] == "none"
    assert index["external_skill_activation_allowed"] is False
    assert index["external_agent_activation_allowed"] is False
    assert index["external_harness_execution_allowed"] is False
    assert index["provider_runtime_launch_allowed"] is False
    assert index["profile_write_allowed"] is False
    assert index["memory_write_allowed"] is False
    assert index["remote_execution_allowed"] is False
    assert index["raw_source_url_exported"] is False
    assert index["raw_evidence_urls_exported"] is False
    assert index["raw_target_paths_exported"] is False
    assert index["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in index["rows"]}
    assert set(rows) == {
        "p1-skill-route-discovery-index",
        "p2-skill-route-discovery-test-fixtures",
        "p3-game-frontend-skill-profile",
        "p4-skill-ecosystem-state-handoff-profile",
    }
    assert rows["p1-skill-route-discovery-index"]["proposal_kind"] == "documentation"
    assert rows["p1-skill-route-discovery-index"]["candidate_names"] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert rows["p1-skill-route-discovery-index"]["selected_local_lane"] == "documentation"
    assert rows["p2-skill-route-discovery-test-fixtures"]["proposal_kind"] == "test"
    assert rows["p2-skill-route-discovery-test-fixtures"]["selected_local_lane"] == "test"
    assert rows["p3-game-frontend-skill-profile"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["p3-game-frontend-skill-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p3-game-frontend-skill-profile"]["selected_local_lane"] == "documentation"
    assert rows["p4-skill-ecosystem-state-handoff-profile"]["candidate_names"] == ["compass-skills"]
    assert rows["p4-skill-ecosystem-state-handoff-profile"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert rows["p4-skill-ecosystem-state-handoff-profile"]["selected_local_lane"] == "config"

    for row in index["rows"]:
        assert row["status"] == "ready"
        assert row["route_hint"] == "skill_route_discovery"
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["selected_evidence_item_ids"]
        assert row["activation_blockers"] == []
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    adjacent = index["adjacent_general_agent_rows"][0]
    assert adjacent["proposal_id"] == "p5-agent-project-harness-eval-doc"
    assert adjacent["item_id"] == "p5-qwen-agentworld-general-agent-project"
    assert adjacent["name"] == "Qwen-AgentWorld"
    assert adjacent["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent["skill_route_discovery_inherited"] is False
    assert adjacent["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert adjacent["selected_local_lane"] == "documentation"
    assert adjacent["direct_runtime_route_allowed"] is False
    assert adjacent["direct_code_patch_route_allowed"] is False
    assert adjacent["external_agent_activation_allowed"] is False
    assert adjacent["external_harness_execution_allowed"] is False
    assert adjacent["provider_runtime_launch_allowed"] is False
    assert adjacent["remote_execution_allowed"] is False

    serialized = json.dumps(index, sort_keys=True)
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_pass2_route_classification_fixture_is_bounded():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass2_route_classification_fixture.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry(payload["candidates"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "invalid_candidates_present"
    assert registry["candidate_count"] == 3
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 3

    candidates_by_name = {candidate["name"]: candidate for candidate in registry["candidates"]}
    assert candidates_by_name["zhengxi-views"]["route_profiles"] == ["generic_skill_workflow"]
    assert candidates_by_name["zhengxi-views"]["source_layout_signals"] == [
        "skill_markdown",
        "validation_script",
    ]
    assert candidates_by_name["zhengxi-views"]["validation_errors"] == [
        "unsupported_candidate_lanes:provider_runtime"
    ]
    assert candidates_by_name["threejs-game-skills"]["validation_errors"] == [
        "unsupported_candidate_lanes:runtime_execution"
    ]
    assert candidates_by_name["compass-skills"]["validation_errors"] == [
        "unsupported_candidate_lanes:install"
    ]

    assert lane_map["proposal_lane_count"] == 12
    assert lane_map["downgraded_candidate_count"] == 3
    assert lane_map["rejected_candidate_count"] == 0
    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])

    fixture_lane = lane_map["pass2_fixture_validation_lane"]
    assert fixture_lane["controller_surface"] == "skill_route_discovery_pass2_fixture_validation_lane"
    assert fixture_lane["status"] == "ready"
    assert fixture_lane["decision"] == "pass2_route_fixtures_ready_for_bounded_local_validation"
    assert fixture_lane["capability_pass"] == 2
    assert fixture_lane["review_gate"] == "focused-evidence-review"
    assert fixture_lane["candidate_count"] == 3
    assert fixture_lane["ready_candidate_count"] == 3
    assert fixture_lane["blocked_candidate_names"] == []
    assert fixture_lane["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert fixture_lane["selected_local_lanes"] == ["documentation", "config", "test"]
    assert fixture_lane["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert fixture_lane["required_evidence"] == [
        "route_classification_fixture",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
    ]
    assert fixture_lane["local_validation_required"] is True
    assert fixture_lane["runtime_action"] == "none"
    assert fixture_lane["external_skill_activation_allowed"] is False
    assert fixture_lane["external_harness_execution_allowed"] is False
    assert fixture_lane["provider_runtime_launch_allowed"] is False
    assert fixture_lane["remote_execution_allowed"] is False
    assert fixture_lane["raw_source_url_exported"] is False
    assert fixture_lane["raw_evidence_urls_exported"] is False
    assert fixture_lane["raw_target_paths_exported"] is False
    assert fixture_lane["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in fixture_lane["rows"]}
    assert rows["zhengxi-views"]["route_profiles"] == ["generic_skill_workflow"]
    assert rows["zhengxi-views"]["selected_local_lane"] == "documentation"
    assert rows["zhengxi-views"]["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-generic"
    ]
    assert rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows["compass-skills"]["selected_local_lane"] == "config"

    for row in rows.values():
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert row["route_hint"] == "skill_route_discovery"
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["fixture_status"] == "ready"
        assert row["activation_blockers"] == []
        assert row["candidate_source_hash"].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    profile_handoff = lane_map["pass2_profile_lane_handoff"]
    assert profile_handoff["controller_surface"] == "skill_route_discovery_pass2_profile_lane_handoff"
    assert profile_handoff["status"] == "ready"
    assert profile_handoff["decision"] == "pass2_profiles_ready_for_operator_replay"
    assert profile_handoff["capability_pass"] == 2
    assert profile_handoff["review_gate"] == "focused-evidence-review"
    assert profile_handoff["operator_handoff"] == "external_supervisor_replay_before_activation"
    assert profile_handoff["proposal_count"] == 3
    assert profile_handoff["ready_proposal_count"] == 3
    assert profile_handoff["blocked_proposal_ids"] == []
    assert profile_handoff["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert profile_handoff["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert profile_handoff["selected_local_lanes"] == ["documentation", "config", "test"]
    assert profile_handoff["downgraded_lane_names"] == [
        "install",
        "provider_runtime",
        "runtime_execution",
    ]
    assert profile_handoff["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture"
    ]
    assert profile_handoff["required_evidence"] == [
        "route_classification_fixture",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "changed_file_review",
    ]
    assert profile_handoff["local_validation_required"] is True
    assert profile_handoff["runtime_action"] == "none"
    assert profile_handoff["external_skill_activation_allowed"] is False
    assert profile_handoff["external_harness_execution_allowed"] is False
    assert profile_handoff["provider_runtime_launch_allowed"] is False
    assert profile_handoff["remote_execution_allowed"] is False
    assert profile_handoff["profile_write_allowed"] is False
    assert profile_handoff["memory_write_allowed"] is False
    assert profile_handoff["raw_source_url_exported"] is False
    assert profile_handoff["raw_evidence_urls_exported"] is False
    assert profile_handoff["raw_target_paths_exported"] is False
    assert profile_handoff["raw_upstream_body_exported"] is False

    handoff_rows = {row["proposal_id"]: row for row in profile_handoff["rows"]}
    assert set(handoff_rows) == {
        "proposal-skill-route-discovery-generic-zhengxi-views",
        "proposal-game-frontend-skill-profile-doc-test",
        "proposal-skill-ecosystem-state-handoff-config-doc",
    }
    assert handoff_rows["proposal-skill-route-discovery-generic-zhengxi-views"][
        "route_profiles"
    ] == ["generic_skill_workflow"]
    assert handoff_rows["proposal-skill-route-discovery-generic-zhengxi-views"][
        "selected_local_lane"
    ] == "documentation"
    assert handoff_rows["proposal-game-frontend-skill-profile-doc-test"]["route_profiles"] == [
        "game_frontend_workflow"
    ]
    assert handoff_rows["proposal-game-frontend-skill-profile-doc-test"]["selected_local_lane"] == "test"
    assert handoff_rows["proposal-skill-ecosystem-state-handoff-config-doc"][
        "route_profiles"
    ] == ["skill_ecosystem_state_handoff"]
    assert handoff_rows["proposal-skill-ecosystem-state-handoff-config-doc"][
        "selected_local_lane"
    ] == "config"

    serialized_handoff = json.dumps(profile_handoff, sort_keys=True)
    assert "https://github.com/" not in serialized_handoff
    for row in handoff_rows.values():
        assert row["status"] == "ready"
        assert row["candidate_source_hashes"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert row["selected_evidence_item_ids"]
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["activation_blockers"] == []
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    growth_summary = lane_map["growth_route_summary_artifact"]
    assert growth_summary["controller_surface"] == "skill_route_discovery_growth_route_summary_artifact"
    assert growth_summary["status"] == "ready"
    assert growth_summary["decision"] == "summarize_pass2_skill_routes_for_operator_review"
    assert growth_summary["capability_pass"] == 2
    assert growth_summary["review_gate"] == "focused-evidence-review"
    assert growth_summary["artifact_contract"] == "body_free_hash_only_growth_route_summary"
    assert growth_summary["candidate_count"] == 3
    assert growth_summary["proposal_count"] == 3
    assert growth_summary["ready_proposal_count"] == 3
    assert growth_summary["blocked_proposal_ids"] == []
    assert growth_summary["observed_route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert growth_summary["selected_local_lanes"] == ["documentation", "config", "test"]
    assert growth_summary["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert growth_summary["downgraded_lane_names"] == [
        "install",
        "provider_runtime",
        "runtime_execution",
    ]
    assert growth_summary["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-profile",
        "p3-skill-ecosystem-handoff-config",
    ]
    assert growth_summary["validation_targets"] == [
        "generic_skill_workflow_fixture_stays_bounded",
        "game_frontend_workflow_profile_maps_to_local_validation",
        "skill_ecosystem_state_handoff_maps_to_metadata_only_config",
    ]
    assert growth_summary["source_surface_statuses"] == {
        "pass2_fixture_validation_lane": "ready",
        "pass2_profile_lane_handoff": "ready",
        "pass2_validation_handoff": "ready",
    }
    assert growth_summary["required_evidence"] == [
        "route_classification_fixture",
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "changed_file_review",
        "review_note",
    ]
    assert growth_summary["operator_handoff"] == "external_supervisor_review_before_activation"
    assert growth_summary["local_validation_required"] is True
    assert growth_summary["runtime_action"] == "none"
    assert growth_summary["external_skill_activation_allowed"] is False
    assert growth_summary["external_agent_activation_allowed"] is False
    assert growth_summary["external_harness_execution_allowed"] is False
    assert growth_summary["provider_runtime_launch_allowed"] is False
    assert growth_summary["remote_execution_allowed"] is False
    assert growth_summary["profile_write_allowed"] is False
    assert growth_summary["memory_write_allowed"] is False
    assert growth_summary["raw_source_url_exported"] is False
    assert growth_summary["raw_evidence_urls_exported"] is False
    assert growth_summary["raw_target_paths_exported"] is False
    assert growth_summary["raw_upstream_body_exported"] is False
    assert growth_summary["raw_replay_commands_exported"] is False
    assert all(command_hash.startswith("sha256:") for command_hash in growth_summary["replay_command_hashes"])

    serialized_summary = json.dumps(growth_summary, sort_keys=True)
    assert "https://github.com/" not in serialized_summary
    assert "python -m pytest" not in serialized_summary
    summary_rows = {row["proposal_id"]: row for row in growth_summary["rows"]}
    assert set(summary_rows) == set(handoff_rows)
    for row in summary_rows.values():
        assert row["status"] == "ready"
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["candidate_source_hashes"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert row["selected_evidence_item_ids"]
        assert row["replay_command_hash"].startswith("sha256:")
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False
        assert row["raw_replay_command_exported"] is False


def test_skill_route_discovery_pass4_local_lane_validation_closes_current_skill_window():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_pass2_focused_evidence_review.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    pass4 = lane_map["pass4_local_lane_validation"]
    assert pass4["controller_surface"] == "skill_route_discovery_pass4_local_lane_validation"
    assert pass4["status"] == "ready"
    assert pass4["decision"] == "complete_skill_route_slice_with_bounded_local_lanes"
    assert pass4["proposal_ids"] == [
        "proposal-skill-route-discovery-generic-001",
        "proposal-skill-route-discovery-game-frontend-002",
        "proposal-skill-state-handoff-003",
    ]
    assert pass4["operator_handoff"] == "external_supervisor_replay_before_activation"
    assert pass4["capability_slice_complete"] is True
    assert pass4["required_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert pass4["covered_route_profiles"] == pass4["required_route_profiles"]
    assert pass4["missing_route_profiles"] == []
    assert pass4["candidate_count"] == 3
    assert pass4["ready_candidate_count"] == 3
    assert pass4["adjacent_general_agent_count"] == 0
    assert pass4["blocked_candidate_names"] == []
    assert pass4["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert pass4["selected_local_lanes"] == ["config", "test"]
    assert pass4["replay_commands"] == [
        "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
        "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
        "python -m pytest tests/test_skill_routing.py -q -k source_cited_domain_research",
    ]
    assert pass4["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "review_note",
    ]
    assert (
        pass4["completion_recovery_workflow"]
        == "run_pass4_replay_commands_then_recheck_pass4_local_lane_validation"
    )
    assert pass4["activation_boundary"] == (
        "supervisor_may_review_local_diff_after_replay; "
        "kernel_does_not_restart_or_activate_external_skills"
    )
    assert pass4["local_validation_required"] is True
    assert pass4["runtime_action"] == "none"
    assert pass4["external_skill_activation_allowed"] is False
    assert pass4["external_harness_execution_allowed"] is False
    assert pass4["provider_runtime_launch_allowed"] is False
    assert pass4["remote_execution_allowed"] is False
    assert pass4["raw_source_url_exported"] is False
    assert pass4["raw_evidence_urls_exported"] is False
    assert pass4["raw_target_paths_exported"] is False
    assert pass4["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in pass4["rows"]}
    assert set(rows) == {"compass-skills", "threejs-game-skills", "zhengxi-views"}
    assert rows["compass-skills"]["route_hint"] == "skill_route_discovery"
    assert rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["compass-skills"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert rows["zhengxi-views"]["route_profiles"] == ["source_cited_domain_research"]
    assert rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert rows["zhengxi-views"]["validation_target"] == "source_citation_and_advice_boundary_check"
    assert rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert rows["threejs-game-skills"]["validation_target"] == "local_frontend_render_or_workflow_check"

    for row in rows.values():
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["row_status"] == "ready"
        assert row["candidate_source_hash"].startswith("sha256:")
        assert all(item_id.startswith(("p1-", "p2-", "p3-")) for item_id in row["selected_evidence_item_ids"])
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    assert pass4["general_agent_project_policy"] == {
        "proposal_id": "p4-p5-agent-harness-eval-queue",
        "when": "general_agent_project_without_skill_workflow_signal",
        "evaluation_lane": "agent_harness_eval_required",
        "allowed_local_lanes": [],
        "direct_local_change_proposals_allowed": False,
        "required_before_implementation": "local_agent_harness_eval_route_established",
        "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_upstream_body_exported": False,
    }

    handoff = lane_map["pass4_completion_handoff"]
    assert handoff["controller_surface"] == "skill_route_discovery_pass4_completion_handoff"
    assert handoff["status"] == "ready"
    assert handoff["decision"] == "handoff_current_skill_route_window_to_supervisor_replay"
    assert handoff["depends_on_controller_surface"] == "skill_route_discovery_pass4_local_lane_validation"
    assert handoff["capability_slice_complete"] is True
    assert handoff["handoff_mode"] == "external_supervisor_replay_without_kernel_restart"
    assert handoff["candidate_count"] == 3
    assert handoff["ready_candidate_count"] == 3
    assert handoff["adjacent_general_agent_count"] == 0
    assert handoff["blocked_candidate_names"] == []
    assert handoff["covered_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert handoff["selected_local_lanes"] == ["config", "test"]
    assert handoff["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert len(handoff["replay_command_hashes"]) == 3
    assert all(command_hash.startswith("sha256:") for command_hash in handoff["replay_command_hashes"])
    assert handoff["rollback_contract"] == {
        "rollback_ref_required": True,
        "rollback_artifact_required": True,
        "rollback_execution": "explicit_destructive_operator_action_only",
    }
    assert handoff["adjacent_general_agent_project_boundary"] == {
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "direct_local_change_proposals_allowed": False,
        "required_before_implementation": "local_agent_harness_eval_route_established",
        "allowed_local_lanes_after_eval": [],
        "adjacent_record_count": 0,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    assert [step["step"] for step in handoff["operator_steps"]] == [
        "verify_rollback_ref_and_artifact",
        "run_pass4_replay_commands",
        "inspect_changed_files_against_selected_lanes",
        "confirm_external_activation_boundary",
        "handoff_to_configured_supervisor",
    ]
    assert all(step["recovery_hint_code"] for step in handoff["operator_steps"])
    assert handoff["activation_boundary"] == (
        "supervisor_may_review_local_diff_after_replay; "
        "kernel_does_not_restart_or_activate_external_skills"
    )
    assert handoff["local_validation_required"] is True
    assert handoff["runtime_action"] == "none"
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["external_harness_execution_allowed"] is False
    assert handoff["provider_runtime_launch_allowed"] is False
    assert handoff["remote_execution_allowed"] is False
    assert handoff["raw_source_url_exported"] is False
    assert handoff["raw_evidence_urls_exported"] is False
    assert handoff["raw_target_paths_exported"] is False
    assert handoff["raw_upstream_body_exported"] is False

    handoff_rows = {row["candidate_name"]: row for row in handoff["rows"]}
    assert set(handoff_rows) == {"compass-skills", "threejs-game-skills", "zhengxi-views"}
    assert handoff_rows["compass-skills"]["selected_local_lane"] == "config"
    assert handoff_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert handoff_rows["zhengxi-views"]["selected_local_lane"] == "test"
    for row in handoff_rows.values():
        assert row["row_status"] == "ready"
        assert row["candidate_source_hash"].startswith("sha256:")
        assert row["replay_command_hash"].startswith("sha256:")
        assert row["inspection_requirements"] == [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "changed_file_review_against_selected_lane",
            "focused_local_validation_result",
            "rollback_artifact_and_ref",
            "review_note_for_uncertainty_or_blockers",
        ]
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    replay_manifest = lane_map["pass4_operator_replay_manifest"]
    assert replay_manifest["controller_surface"] == "skill_route_discovery_pass4_operator_replay_manifest"
    assert replay_manifest["status"] == "ready"
    assert replay_manifest["decision"] == "supervisor_can_replay_selected_local_lanes_before_activation_review"
    assert replay_manifest["depends_on_controller_surface"] == "skill_route_discovery_pass4_completion_handoff"
    assert replay_manifest["handoff_mode"] == "body_free_operator_replay_manifest"
    assert replay_manifest["candidate_count"] == 3
    assert replay_manifest["ready_candidate_count"] == 3
    assert replay_manifest["selected_local_lanes"] == ["config", "test"]
    assert [row["lane"] for row in replay_manifest["lane_artifact_targets"]] == ["config", "test"]
    assert [row["artifact_target_count"] for row in replay_manifest["lane_artifact_targets"]] == [1, 2]
    for row in replay_manifest["lane_artifact_targets"]:
        assert all(target_hash.startswith("sha256:") for target_hash in row["artifact_target_hashes"])
        assert row["changed_file_review"] == "must_match_selected_lane_or_be_recorded_as_review_note"
    assert replay_manifest["replay_command_hashes"] == handoff["replay_command_hashes"]
    assert [row["candidate_name"] for row in replay_manifest["candidate_rows"]] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert replay_manifest["operator_replay_requirements"] == [
        "confirm_rollback_ref_and_artifact",
        "run_selected_lane_replay_commands_from_pass4_local_lane_validation",
        "compare_changed_files_with_hashed_lane_artifact_targets",
        "record_any_unmatched_file_as_review_note_or_blocker",
        "keep_activation_external_to_the_kernel",
    ]
    assert replay_manifest["completion_blocker_hints"] == [
        "rollback_contract_missing",
        "pass4_replay_not_confirmed",
        "lane_artifact_review_missing",
        "external_activation_boundary_weakened",
    ]
    assert replay_manifest["local_validation_required"] is True
    assert replay_manifest["runtime_action"] == "none"
    assert replay_manifest["external_skill_activation_allowed"] is False
    assert replay_manifest["external_harness_execution_allowed"] is False
    assert replay_manifest["provider_runtime_launch_allowed"] is False
    assert replay_manifest["remote_execution_allowed"] is False
    assert replay_manifest["raw_source_url_exported"] is False
    assert replay_manifest["raw_evidence_urls_exported"] is False
    assert replay_manifest["raw_target_paths_exported"] is False
    assert replay_manifest["raw_upstream_body_exported"] is False
    assert replay_manifest["raw_replay_command_exported"] is False


def test_skill_route_discovery_pass4_completion_handoff_queues_adjacent_general_agent_evidence():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_window_pass4_completion_handoff.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["evidence_item_count"] == 4
    assert registry["candidate_count"] == 3
    assert registry["ignored_evidence_item_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0

    ignored = registry["ignored_evidence_items"][0]
    assert ignored["item_id"] == "p3-qwen-agentworld-general-agent"
    assert ignored["name"] == "Qwen-AgentWorld"
    assert ignored["ignored_reason"] == "route_hint_not_skill_route_discovery"
    assert ignored["evaluation_lane"] == "agent_harness_eval_required"
    assert ignored["skill_route_discovery_inherited"] is False
    assert ignored["direct_runtime_route_allowed"] is False
    assert ignored["direct_code_patch_route_allowed"] is False

    pass4 = lane_map["pass4_local_lane_validation"]
    assert pass4["status"] == "ready"
    assert pass4["capability_slice_complete"] is True
    assert pass4["covered_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert pass4["missing_route_profiles"] == []
    assert pass4["candidate_count"] == 3
    assert pass4["ready_candidate_count"] == 3
    assert pass4["adjacent_general_agent_count"] == 1
    assert pass4["selected_local_lanes"] == ["config", "test"]
    assert pass4["general_agent_project_policy"]["evaluation_lane"] == "agent_harness_eval_required"
    assert pass4["general_agent_project_policy"]["allowed_local_lanes"] == [
        "documentation",
        "test",
        "code_patch",
    ]
    assert pass4["general_agent_project_policy"]["direct_local_change_proposals_allowed"] is False
    assert pass4["general_agent_project_policy"]["runtime_action"] == "none"

    pass4_rows = {row["candidate_name"]: row for row in pass4["rows"]}
    assert set(pass4_rows) == {"compass-skills", "threejs-game-skills", "zhengxi-views"}
    assert pass4_rows["compass-skills"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert pass4_rows["compass-skills"]["selected_local_lane"] == "config"
    assert pass4_rows["compass-skills"]["selected_evidence_item_ids"] == [
        "p1-compass-skills-skill-route"
    ]
    assert pass4_rows["zhengxi-views"]["route_profiles"] == ["source_cited_domain_research"]
    assert pass4_rows["zhengxi-views"]["selected_local_lane"] == "test"
    assert pass4_rows["zhengxi-views"]["selected_evidence_item_ids"] == [
        "p1-zhengxi-views-skill-route"
    ]
    assert pass4_rows["threejs-game-skills"]["route_profiles"] == ["game_frontend_workflow"]
    assert pass4_rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert pass4_rows["threejs-game-skills"]["selected_evidence_item_ids"] == [
        "p1-threejs-game-skills-route"
    ]

    for row in pass4_rows.values():
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["row_status"] == "ready"
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    adjacent_row = pass4["adjacent_general_agent_rows"][0]
    assert adjacent_row["proposal_id"] == "p3-agent-harness-eval-for-general-agent-projects"
    assert adjacent_row["item_id"] == "p3-qwen-agentworld-general-agent"
    assert adjacent_row["evaluation_lane"] == "agent_harness_eval_required"
    assert adjacent_row["skill_route_discovery_inherited"] is False
    assert adjacent_row["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert adjacent_row["direct_runtime_route_allowed"] is False
    assert adjacent_row["direct_code_patch_route_allowed"] is False
    assert adjacent_row["required_before_implementation"] == "local_agent_harness_eval_route_established"
    assert adjacent_row["runtime_action"] == "none"
    assert adjacent_row["external_agent_activation_allowed"] is False
    assert adjacent_row["external_harness_execution_allowed"] is False

    handoff = lane_map["pass4_completion_handoff"]
    assert handoff["status"] == "ready"
    assert handoff["decision"] == "handoff_current_skill_route_window_to_supervisor_replay"
    assert handoff["capability_slice_complete"] is True
    assert handoff["adjacent_general_agent_count"] == 1
    assert handoff["adjacent_general_agent_project_boundary"] == {
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "direct_local_change_proposals_allowed": False,
        "required_before_implementation": "local_agent_harness_eval_route_established",
        "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
        "adjacent_record_count": 1,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    handoff_adjacent_row = handoff["adjacent_general_agent_rows"][0]
    assert handoff_adjacent_row["item_id"] == adjacent_row["item_id"]
    assert handoff_adjacent_row["source_hash"] == adjacent_row["source_hash"]
    assert handoff_adjacent_row["evaluation_lane"] == "agent_harness_eval_required"
    assert handoff_adjacent_row["skill_route_discovery_inherited"] is False
    assert handoff_adjacent_row["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert handoff_adjacent_row["direct_runtime_route_allowed"] is False
    assert handoff_adjacent_row["direct_code_patch_route_allowed"] is False
    assert handoff_adjacent_row["runtime_action"] == "none"
    assert "replay_command" not in handoff_adjacent_row

    serialized = json.dumps(handoff, sort_keys=True)
    assert "https://github.com/" not in serialized
    assert "runtime_execution" not in serialized
    assert "install" not in serialized

    replay_manifest = lane_map["pass4_operator_replay_manifest"]
    assert replay_manifest["status"] == "ready"
    assert replay_manifest["adjacent_general_agent_project_boundary"] == {
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
        "adjacent_record_count": 1,
        "required_before_implementation": "local_agent_harness_eval_route_established",
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    serialized_manifest = json.dumps(replay_manifest, sort_keys=True)
    assert "https://github.com/" not in serialized_manifest
    assert "runtime_execution" not in serialized_manifest
    assert "install" not in serialized_manifest

    completion_matrix = lane_map["active_pass4_completion_matrix"]
    assert completion_matrix["controller_surface"] == "skill_route_discovery_active_pass4_completion_matrix"
    assert completion_matrix["status"] == "ready"
    assert completion_matrix["decision"] == "active_pass4_skill_route_proposals_ready_for_supervisor_replay"
    assert completion_matrix["depends_on_controller_surfaces"] == [
        "skill_route_discovery_pass4_completion_handoff",
        "skill_route_discovery_pass4_operator_replay_manifest",
    ]
    assert completion_matrix["source_digest"] == "github-growth-20260628T000729.525285Z"
    assert completion_matrix["capability_pass"] == 4
    assert completion_matrix["total_passes"] == 4
    assert completion_matrix["capability_slice_complete"] is True
    assert completion_matrix["review_gate"] == "focused-evidence-review"
    assert completion_matrix["proposal_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-game-skill-workflow-profile",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert completion_matrix["ready_proposal_count"] == 3
    assert completion_matrix["blocked_proposal_ids"] == []
    assert completion_matrix["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert completion_matrix["selected_local_lanes"] == ["documentation", "config", "test"]
    assert completion_matrix["required_evidence"] == [
        "selected_item_ids_or_frozen_fixture",
        "body_free_repository_summary",
        "rollback_artifact",
        "focused_local_validation",
        "controller_recomputed_gates",
        "review_note",
    ]
    assert completion_matrix["operator_handoff"] == "external_supervisor_replay_without_kernel_restart"
    assert completion_matrix["adjacent_general_agent_project_boundary"] == {
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
        "adjacent_record_count": 1,
        "required_before_implementation": "local_agent_harness_eval_route_established",
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    assert completion_matrix["local_validation_required"] is True
    assert completion_matrix["runtime_action"] == "none"
    assert completion_matrix["external_skill_activation_allowed"] is False
    assert completion_matrix["external_agent_activation_allowed"] is False
    assert completion_matrix["external_harness_execution_allowed"] is False
    assert completion_matrix["provider_runtime_launch_allowed"] is False
    assert completion_matrix["profile_write_allowed"] is False
    assert completion_matrix["memory_write_allowed"] is False
    assert completion_matrix["remote_execution_allowed"] is False
    assert completion_matrix["raw_replay_commands_exported"] is False
    assert completion_matrix["raw_source_url_exported"] is False
    assert completion_matrix["raw_evidence_urls_exported"] is False
    assert completion_matrix["raw_target_paths_exported"] is False
    assert completion_matrix["raw_upstream_body_exported"] is False

    matrix_rows = {row["proposal_id"]: row for row in completion_matrix["rows"]}
    assert set(matrix_rows) == set(completion_matrix["proposal_ids"])
    assert matrix_rows["p1-skill-route-discovery-generic"]["proposal_kind"] == "test"
    assert matrix_rows["p1-skill-route-discovery-generic"]["selected_local_lane"] == "test"
    assert matrix_rows["p1-skill-route-discovery-generic"]["route_profiles"] == ["source_cited_domain_research"]
    assert matrix_rows["p2-game-skill-workflow-profile"]["proposal_kind"] == "documentation"
    assert matrix_rows["p2-game-skill-workflow-profile"]["proposal_track"] == "game_frontend_workflow"
    assert matrix_rows["p2-game-skill-workflow-profile"]["candidate_names"] == ["threejs-game-skills"]
    assert matrix_rows["p2-game-skill-workflow-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert matrix_rows["p2-game-skill-workflow-profile"]["selected_local_lane"] == "documentation"
    assert matrix_rows["p2-game-skill-workflow-profile"]["validation_target"] == (
        "game_frontend_workflow_profile_documentation_review"
    )
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["proposal_kind"] == "config"
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["proposal_track"] == "skill_ecosystem_state_handoff"
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["candidate_names"] == ["compass-skills"]
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "config"
    assert matrix_rows["p3-skill-ecosystem-state-handoff"]["validation_target"] == (
        "skill_ecosystem_state_handoff_metadata_only_config"
    )

    for row in matrix_rows.values():
        assert row["status"] == "ready"
        assert row["activation_blockers"] == []
        assert row["route_hint"] == SKILL_ROUTE_DISCOVERY_HINT
        assert row["route_class"] == SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["selected_evidence_item_ids"]
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert all(command_hash.startswith("sha256:") for command_hash in row["replay_command_hashes"])
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_replay_commands_exported"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    serialized_matrix = json.dumps(completion_matrix, sort_keys=True)
    assert "https://github.com/" not in serialized_matrix
    assert "runtime_execution" not in serialized_matrix
    assert "install" not in serialized_matrix


def test_skill_route_discovery_current_run_pass4_completion_matrix_matches_proposals():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "skill_route_discovery"
        / "current_run_pass4_skill_route_completion.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    registry = build_skill_route_discovery_registry_from_evidence_items(payload["items"])
    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    completion_matrix = lane_map["active_pass4_completion_matrix"]
    assert completion_matrix["status"] == "ready"
    assert completion_matrix["source_digest"] == "github-growth-20260628T000729.525285Z"
    assert completion_matrix["proposal_ids"] == [
        "p1-skill-route-discovery-generic",
        "p2-game-skill-workflow-profile",
        "p3-skill-ecosystem-state-handoff",
    ]
    assert completion_matrix["ready_proposal_count"] == 3
    assert completion_matrix["blocked_proposal_ids"] == []
    assert completion_matrix["selected_local_lanes"] == ["documentation", "config", "test"]
    assert completion_matrix["operator_handoff"] == "external_supervisor_replay_without_kernel_restart"
    assert completion_matrix["runtime_action"] == "none"
    assert completion_matrix["external_skill_activation_allowed"] is False
    assert completion_matrix["external_agent_activation_allowed"] is False
    assert completion_matrix["external_harness_execution_allowed"] is False
    assert completion_matrix["provider_runtime_launch_allowed"] is False
    assert completion_matrix["profile_write_allowed"] is False
    assert completion_matrix["memory_write_allowed"] is False
    assert completion_matrix["remote_execution_allowed"] is False
    assert completion_matrix["raw_source_url_exported"] is False
    assert completion_matrix["raw_evidence_urls_exported"] is False
    assert completion_matrix["raw_target_paths_exported"] is False
    assert completion_matrix["raw_upstream_body_exported"] is False

    rows = {row["proposal_id"]: row for row in completion_matrix["rows"]}
    assert rows["p1-skill-route-discovery-generic"]["route_profiles"] == ["generic_skill_workflow"]
    assert rows["p1-skill-route-discovery-generic"]["selected_local_lane"] == "test"
    assert rows["p1-skill-route-discovery-generic"]["selected_evidence_item_ids"] == [
        "p1-skill-route-discovery-generic"
    ]
    assert rows["p2-game-skill-workflow-profile"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows["p2-game-skill-workflow-profile"]["selected_local_lane"] == "documentation"
    assert rows["p2-game-skill-workflow-profile"]["selected_evidence_item_ids"] == [
        "p2-game-skill-workflow-profile"
    ]
    assert rows["p3-skill-ecosystem-state-handoff"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert rows["p3-skill-ecosystem-state-handoff"]["selected_local_lane"] == "config"
    assert rows["p3-skill-ecosystem-state-handoff"]["selected_evidence_item_ids"] == [
        "p3-skill-ecosystem-state-handoff"
    ]

    for row in rows.values():
        assert row["status"] == "ready"
        assert row["activation_blockers"] == []
        assert set(row["allowed_local_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert all(source_hash.startswith("sha256:") for source_hash in row["candidate_source_hashes"])
        assert all(command_hash.startswith("sha256:") for command_hash in row["replay_command_hashes"])
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["profile_write_allowed"] is False
        assert row["memory_write_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_replay_commands_exported"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    serialized_matrix = json.dumps(completion_matrix, sort_keys=True)
    assert "https://github.com/" not in serialized_matrix
    assert "runtime_execution" not in serialized_matrix
    assert "install" not in serialized_matrix


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


def test_skill_route_discovery_zhengxi_skill_metadata_maps_to_bounded_local_lanes():
    registry = build_skill_route_discovery_registry_from_summaries(
        [
            {
                "name": "zhengxi-views",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "summary": (
                    "Source-cited domain research agent skill with traceable public views, "
                    "fund data references, evals, scripts, advice disclaimer, and validation notes."
                ),
                "topics": ["agent-skill", "research", "fund", "source-cited"],
                "suggested_lanes": ["documentation", "config", "test", "code_patch", "install"],
                "observed_paths": [
                    "SKILL.md",
                    "skill.yml",
                    "README.md",
                    "references/corpus/index.md",
                    "references/fund_data/snapshot.json",
                    "evals/source_citation_eval.yaml",
                    "scripts/validate_references.py",
                ],
                "metadata_files": ["skill.yml"],
            }
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)

    assert registry["registry_status"] == "classification_only"
    assert registry["candidate_count"] == 1
    assert registry["enabled_candidate_count"] == 0
    assert registry["executable_skill_count"] == 0
    assert registry["invalid_candidate_count"] == 0

    candidate = registry["candidates"][0]
    assert candidate["name"] == "zhengxi-views"
    assert candidate["route_hints"] == ["skill_route_discovery"]
    assert candidate["route_profiles"] == ["source_cited_domain_research"]
    assert set(candidate["candidate_lanes"]) == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert candidate["source_layout_signals"] == [
        "skill_markdown",
        "validation_script",
    ]
    assert candidate["requested_actions"] == []
    assert candidate["enabled"] is False
    assert candidate["validation_errors"] == []

    assert lane_map["proposal_lane_count"] == 4
    assert lane_map["rejected_candidate_count"] == 0
    assert lane_map["downgraded_candidate_count"] == 0
    inventory = lane_map["candidate_lane_inventory"][0]
    assert inventory["candidate_name"] == "zhengxi-views"
    assert inventory["route_profiles"] == ["source_cited_domain_research"]
    assert inventory["proposal_kinds"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert inventory["handoff_metadata"]["selected_local_lane"] == "test"
    assert inventory["route_validation_contract"]["rows"][0]["validation_gate"] == (
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    )
    assert inventory["local_validation_required"] is True
    assert inventory["runtime_action"] == "none"
    assert inventory["external_skill_activation_allowed"] is False
    assert inventory["handoff_metadata"]["external_harness_execution_allowed"] is False
    assert inventory["handoff_metadata"]["provider_runtime_launch_allowed"] is False

    assert {
        lane["proposal_kind"]
        for lane in lane_map["proposal_lanes"]
    } == set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert all(lane["route_hint"] == "skill_route_discovery" for lane in lane_map["proposal_lanes"])
    assert all(lane["local_validation_required"] is True for lane in lane_map["proposal_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in lane_map["proposal_lanes"])
    assert all(lane["external_skill_activation_allowed"] is False for lane in lane_map["proposal_lanes"])


def test_skill_route_discovery_bounded_route_profile_matrix_covers_skill_workflow_lanes():
    registry = build_skill_route_discovery_registry_from_evidence_items(
        [
            {
                "item_id": "generic-skill-workflow",
                "item_kind": "repository",
                "name": "minimal-skill-note",
                "source_url": "https://github.com/example/minimal-skill-note",
                "title": "Minimal public agent skill note",
                "summary": "Small public agent skill note with local documentation evidence only.",
                "route_hints": ["skill_route_discovery", "runtime_execution"],
                "topics": ["skills"],
                "suggested_lanes": ["documentation", "install", "runtime_execution"],
            },
            {
                "item_id": "state-handoff-skill",
                "item_kind": "repository",
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "title": "COMPASS Skills state handoff profile",
                "summary": "Skill ecosystem with task forest, local memory, collaboration profile, handoff, and privacy boundary.",
                "route_hints": ["skill_route_discovery", "provider_runtime"],
                "topics": ["skills", "memory", "profile"],
                "suggested_lanes": ["config", "test", "install"],
            },
            {
                "item_id": "game-frontend-skill",
                "item_kind": "repository",
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "title": "Three.js game skills director",
                "summary": "Three.js browser game workflow skills with frontend QA, gameplay validation, and asset boundary notes.",
                "route_hints": ["skill_route_discovery", "external_harness"],
                "topics": ["threejs", "game", "skills"],
                "suggested_lanes": ["test", "documentation", "execute"],
            },
        ]
    )

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)
    matrix = lane_map["bounded_route_profile_matrix"]
    rows = {row["route_profile"]: row for row in matrix["rows"]}

    assert matrix["controller_surface"] == "skill_route_discovery_bounded_route_profile_matrix"
    assert matrix["status"] == "ready"
    assert matrix["decision"] == "route_profiles_mapped_to_bounded_local_lanes"
    assert matrix["required_profiles"] == [
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert matrix["covered_required_profiles"] == matrix["required_profiles"]
    assert matrix["missing_required_profiles"] == []
    assert matrix["observed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert matrix["allowed_local_lanes"] == list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    assert matrix["runtime_action"] == "none"
    assert matrix["external_skill_activation_allowed"] is False
    assert matrix["external_harness_execution_allowed"] is False
    assert matrix["provider_runtime_launch_allowed"] is False
    assert matrix["remote_execution_allowed"] is False
    assert matrix["raw_source_url_exported"] is False
    assert matrix["raw_evidence_urls_exported"] is False
    assert matrix["raw_target_paths_exported"] is False
    assert matrix["raw_upstream_body_exported"] is False

    assert rows["generic_skill_workflow"]["candidate_names"] == ["minimal-skill-note"]
    assert rows["generic_skill_workflow"]["selected_local_lanes"] == ["documentation"]
    assert rows["generic_skill_workflow"]["validation_targets"] == ["body_free_route_profile_note"]
    assert rows["skill_ecosystem_state_handoff"]["candidate_names"] == ["compass-skills"]
    assert rows["skill_ecosystem_state_handoff"]["selected_local_lanes"] == ["config"]
    assert rows["skill_ecosystem_state_handoff"]["validation_targets"] == ["state_or_profile_boundary_metadata"]
    assert rows["game_frontend_workflow"]["candidate_names"] == ["threejs-game-skills"]
    assert rows["game_frontend_workflow"]["selected_local_lanes"] == ["test"]
    assert rows["game_frontend_workflow"]["validation_targets"] == ["local_frontend_render_or_workflow_check"]

    for row in matrix["rows"]:
        assert set(row["allowed_local_lanes"]) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        assert row["status"] == "ready"
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False


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
            "downgraded_lane_names": ["install", "runtime_execution"],
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
