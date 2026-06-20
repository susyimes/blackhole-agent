# Skill Route Discovery Pass 1 Next Target

- Source digest: `github-growth-20260620T203207.784346Z`
- Capability theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260620T203305.384320-run-a-local-skill-route-discovery-validation-for`
- Rollback ref: `refs/rollback/20260621T043206Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260621T043206Z-skill-route-discovery-pass1.txt`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/baskduf/FableCodex`
- `https://github.com/omnigent-ai/omnigent`

COMPASS exposes local-first clarification, task-memory, handoff, and profile
skills. Three.js Game Skills exposes a director/specialist game workflow with
QA and asset boundaries. FableCodex exposes Codex/workflow/skill signals with
verification habits. Omnigent remains general agent-harness context rather than
a skill-route activation source.

## Hypothesis

Pass-1 skill-route discovery should surface the next bounded local validation
target directly. Grouped lane targets already existed, but supervisors still
had to infer which lane to carry forward from lane order and profile rows.

## Change

- Added `next_validation_target` to `skill_route_discovery_validation_lane_plan`.
- Repeated the same target through `profile_validation_replay`,
  `validation_target_handoff`, and `next_pass_handoff`.
- Kept the target body-free and limited to documentation, config, test, or
  code_patch lanes, with runtime action and external activation denied.
- Updated harness regression tests and operator documentation.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_capability_window_reports_in_progress_before_final_pass or skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff or skill_route_discovery_lane"`: passed, 11 passed.

## Review Notes

- No upstream code, installer, scaffold, browser helper, skill body, profile
  write, provider launch, or remote execution was imported or run.
- The self-model was read and left unchanged. It already favors rollback-backed
  local evolution over report-only work, which matches this pass.
