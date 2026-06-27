# Skill Route Discovery Pass 2: Current Window Local Lanes

Source digest: `github-growth-20260627T104310.675577Z`
Branch: `codex/blackhole-evolve/20260627T104433.034194-add-local-route-discovery-fixtures-for-generic-s`
Rollback: `refs/blackhole-agent/rollback/20260627T104558Z/skill-route-discovery-pass2`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: generic skill workflow / public view evidence for body-free local lane validation.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem state-handoff evidence for metadata-only config validation.
- `https://github.com/majidmanzarpour/threejs-game-skills`: game/frontend skill workflow evidence for local test validation.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent harness pressure; existing agent harness eval route remains separate from skill-route activation.

## Hypothesis

Pass-2 skill-route fixtures are more useful if frozen candidate metadata can carry an explicit route profile. The harness should preserve known bounded profiles from local evidence fixtures before falling back to text inference, and it should reject unknown profile names as validation errors.

## Change

- Added explicit `route_profiles` support to `ExternalSkillRouteCandidate`.
- Unknown explicit route profiles now block the candidate with `unsupported_route_profiles`.
- Added a current-window local harness fixture for generic skill workflow, state handoff, and game frontend profiles.
- Updated the local harness fixture-suite count and result assertion.

The fixture proves pass-2 profile lanes map to `documentation`, `config`, and `test`, keep `code_patch` as an allowed local lane, require local validation, and deny runtime action, external skill activation, external harness execution, provider launch, remote execution, and raw evidence URL export.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or skill_route_discovery_pass2_profile_lane_matrix_covers_generic_skill_profiles"`: passed, 2 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `PYTHONPATH=src python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map or agent_harness_eval_fixture"`: passed, 7 tests.
- `PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k "skill_route or route_classifier or general_agent_project"`: passed, 11 tests.
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 32 tests.

## Review Notes

- Self-model was read and left unchanged. It already prefers rollback-backed, locally validated behavior changes over validation-report-only work, which matches this run.
- No upstream code was cloned, installed, imported, or executed.
- The worktree Python environment resolves to the base checkout unless `PYTHONPATH=src` is set; validation commands above pin imports to this worktree.
