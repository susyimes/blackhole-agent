# Skill Route Pass-2 Profile Lane Matrix

- Source digest: `github-growth-20260623T101652.961949Z`
- Capability theme: `skill-route-discovery`
- Capability pass: 2 of 4
- Branch: `codex/blackhole-evolve/20260623T101833.936414-add-or-extend-local-tests-that-verify-skill-rout`
- Rollback ref: `refs/blackhole-rollback/20260623T101652Z-skill-route-pass2-profile-lanes`
- Rollback artifact: `artifacts/rollback/20260623T101652Z-skill-route-pass2-profile-lanes.md`

## Evidence

- `https://github.com/baskduf/FableCodex`: public repository presents Codex workflow gates, local ledgers, examples, tests, and plugin routing guidance. Local lesson: mixed Codex/workflow/skill evidence should stay on the skill-route path before any secondary harness lane.
- `https://github.com/dongshuyan/compass-skills`: public repository is carried as skill ecosystem/state handoff evidence. Local lesson: route metadata may inform config/test lanes, but profile or memory writes remain blocked without local boundary validation.
- `https://github.com/omnigent-ai/omnigent`: public repository is a general agent framework/meta-harness, not a skill-route source. Local lesson: general harness evidence should not directly authorize skill activation or runtime changes.

## Hypothesis

Pass-2 already had a profile acceptance contract, but the operator-visible handoff packet still required cross-referencing nested surfaces to see how each route profile maps to a bounded local lane. Adding a `profile_lane_matrix` to `pass2_handoff_packet` makes generic skill workflow, COMPASS-style state handoff, game/frontend workflow, and Codex workflow gate evidence replayable as bounded local lanes before activation.

## Changes

- Added `pass2_handoff_packet.profile_lane_matrix` in `src/blackhole_agent/harness_eval.py`.
- Extended pass-2 harness tests to assert the matrix is ready for the existing pass-2 fixture.
- Added an inline focused regression covering `generic_skill_workflow`, `skill_ecosystem_state_handoff`, `game_frontend_workflow`, and `codex_workflow_gate`; it asserts all rows remain within documentation, config, test, or code_patch even when the synthetic handoff is blocked for missing selected replay readiness.
- Updated `docs/skill-route-discovery.md` with the new operator-visible matrix contract.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "pass2_profile_lane_matrix or pass2_fixture_covers_required_profiles_and_next_handoff or validation_readiness_summary_surfaces_selected_lane_without_urls"`: passed, 3 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery or mixed"`: passed, 22 tests.

## Review Notes

- Self-model was read and left unchanged. It already supports rollback-backed, locally validated behavior changes and did not need a run-specific revision.
- The generic-profile inline fixture intentionally remains blocked at pass-2 handoff readiness because it lacks a selected replay queue; this preserves the distinction between bounded lane mapping and activation readiness.
- No upstream skill code was installed, cloned, executed, or activated. Raw evidence URLs are asserted absent from serialized pass-2 packet output.
