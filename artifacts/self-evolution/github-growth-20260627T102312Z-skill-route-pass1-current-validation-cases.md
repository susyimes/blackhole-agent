# Skill Route Pass 1 Current Validation Cases

Source digest: `github-growth-20260627T102312.650770Z`
Capability theme: `skill-route-discovery`
Pass: 1 of 4
Branch: `codex/blackhole-evolve/20260627T102421.235409-add-a-local-skill-route-discovery-validation-cas`
Rollback ref: `refs/blackhole-rollback/20260627T102309Z-skill-route-discovery-pass1-local-lanes`
Rollback artifact: `artifacts/rollback/20260627T102309Z-skill-route-discovery-pass1-local-lanes.md`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: public Python-oriented agent skill/workflow signal; treated as body-free route evidence only.
- `https://github.com/majidmanzarpour/threejs-game-skills`: game/frontend skill workflow signal; bounded before any frontend, scaffold, browser, asset, or provider work.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state-handoff signal; bounded before profile, memory, or state writes.

No upstream code, prompts, installers, scaffolds, provider helpers, browser checks, or skill bodies were copied or executed.

## Hypothesis

The first pass in this window should give operators a direct local validation surface for the active proposal IDs, not only generic route-policy inventory. A pass-specific surface makes it clear which evidence can become local documentation, config, test, or code_patch work before activation, and keeps generic Python skill workflow evidence separate from source-cited domain research boundaries.

## Change

- Added `current_pass_validation_cases` to `build_skill_route_discovery_proposal_lane_map`.
- Mapped `p1_skill_route_discovery_generic_views`, `p2_skill_route_discovery_game_frontend`, and `p3_skill_ecosystem_state_handoff_config` to bounded local lanes, validation targets, and replay commands.
- Added tests for the full current pass window and for a generic-only Python agent-skill workflow signal with matched `agent`, `skill`, and `workflow` terms.
- Documented the new operator surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "current_pass_validation_cases or current_window_pass1_proposal_intake"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 41 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py tests/test_docs_contracts.py`: passed.

## Self-Model

Unchanged. The current self-model already favors rollback-backed local behavior changes while keeping external skill activation, provider launch, remote execution, and privacy-leaking routes outside autonomous activation.

## Review Notes

- This pass does not activate external skills or run upstream repositories.
- `zhengxi-views` can classify as `source_cited_domain_research` when the body-free evidence carries source-cited/domain/advice wording; the new generic test uses a plain Python agent-skill workflow signal to validate the generic route separately.
- Activation remains a supervisor concern after local validation and artifact handoff.
