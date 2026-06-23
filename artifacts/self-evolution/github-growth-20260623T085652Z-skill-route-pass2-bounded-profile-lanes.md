# Skill Route Pass 2 Bounded Profile Lanes

- Source digest: `github-growth-20260623T085652.904208Z`
- Branch: `codex/blackhole-evolve/20260623T085803.129830-add-or-extend-local-validation-for-skill-route-d`
- Rollback ref: `refs/blackhole-rollback/20260623T085652Z-skill-route-pass2-bounded-lanes`
- Rollback artifact: `artifacts/rollback/20260623T085652Z-skill-route-pass2-bounded-lanes.md`

## Evidence

The active capability window carried skill/workflow evidence from:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`

Reusable lesson: skill and workflow repositories should become bounded local validation lanes with route-profile distinctions before activation. The local surface should show which route profiles have documentation, config, test, and code_patch lanes without granting install, execution, provider launch, remote execution, or external skill activation.

## Hypothesis

A body-free `bounded_profile_lane_matrix` in the skill-route harness makes pass-2 operator review clearer by showing required and observed route profiles, selected local lanes, available bounded lanes, and missing-profile diagnostics in one replayable controller surface.

## Changes

- Added `skill_route_discovery_bounded_profile_lane_matrix` to `src/blackhole_agent/harness_eval.py`.
- Included the matrix in `skill_route_discovery_lane` output.
- Documented `bounded_profile_lane_matrix` in `docs/skill-route-discovery.md`.
- Extended pass-2 fixture coverage to assert codex workflow, game frontend, state handoff, and source-cited domain profiles stay inside documentation, config, test, and code_patch lanes.
- Added generic profile coverage for `generic_skill_workflow`.
- Fixed the rollback artifact command fence.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff or bounded_profile_lane_matrix_preserves_generic_profile"`: passed, 2 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_docs_contracts.py -q -k "skill_route_discovery or bounded_profile_lane_matrix"`: passed, 67 tests.
- `PYTHONPATH=src python -m compileall -q src\blackhole_agent tests\test_harness_eval.py`: passed.

## Review Notes

- No upstream code was cloned, installed, run, or imported.
- The new matrix exports hashed source identifiers from existing plan rows and does not export raw evidence URLs, source URLs, target paths, or upstream bodies.
- The self-model was left unchanged; its current preference for rollback-backed local behavior improvements already matches this run.
