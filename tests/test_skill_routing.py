import json
from pathlib import Path

from blackhole_agent.skill_routing import (
    AMBIGUOUS_SKILL_MATCH,
    EXACT_TRIGGER_MATCH,
    SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
    SKILL_ROUTE_DISCOVERY_DISABLED,
    SKILL_ROUTE_DISCOVERY_INVALID,
    NO_SKILL_MATCH,
    ExternalSkillRouteCandidate,
    TOPICAL_MATCH,
    SkillDescriptor,
    build_skill_route_discovery_registry,
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
