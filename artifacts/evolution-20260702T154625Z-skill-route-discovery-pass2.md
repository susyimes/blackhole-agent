# Skill Route Discovery Pass 2

Source digest: `github-growth-20260702T154626.821848Z`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation workflow boundaries, and non-investment-advice limits.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: general-agent project evidence without skill workflow route hints in this run.

## Hypothesis

Pass 2 should expose a replayable local validation lane for current skill-route evidence while keeping adjacent general-agent trends behind `agent_harness_eval_required` until local harness evaluation selects a bounded follow-up lane.

## Changes

- Registered `github-growth-20260702T154626.821848Z` in the pass-2 skill-route controller surface.
- Added frozen skill-route and local harness fixtures for the current digest.
- Added focused regression coverage proving zhengxi-views maps only to documentation, config, test, or code_patch lanes, with no runtime action.
- Updated operator documentation for the pass-2 route split.

## Self-Model

Read `docs/self-model.md` and left it unchanged. It already describes rollback-backed local evolution and a narrow safety boundary, and this run did not produce evidence that it is behavior-shaping beyond policy context.

## Rollback

Rollback ref: `refs/rollback/blackhole-agent/20260702T154625Z-skill-route-discovery-pass2`

Rollback artifact: `artifacts/rollback-20260702T154625Z-skill-route-discovery-pass2.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260702T154626_pass2"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "20260702T154626_pass2"`: passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or skill_route_discovery_lane"`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery_current_digest_20260702T154626_pass2 or current_digest_pass2_local_validation_lane"`: passed.
