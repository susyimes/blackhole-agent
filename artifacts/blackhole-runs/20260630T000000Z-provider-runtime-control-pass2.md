# Provider Runtime Control Pass 2

- Source digest: `github-growth-20260629T161904.226636Z`
- Rollback artifact: `artifacts/rollback/20260630T000000Z-provider-runtime-control-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260630T000000-provider-runtime-control-pass2`
- Evidence trigger URLs:
  - `https://github.com/dongshuyan/compass-skills`
  - `https://github.com/lyra81604/zhengxi-views`

## Hypothesis

Provider-runtime-control windows should not report a skill-route lane as passed when the provider/runtime replay
sample is absent. The operator-facing recovery path should point at provider-runtime preflight replay rather than a
generic local artifact repair caused by the route being blocked.

## Change

- `skill_route_discovery_lane` now applies the existing provider runtime sample gate before lane status is finalized.
- Missing required body-free provider/runtime samples block the lane with
  `provider_runtime_preflight_sample_missing`.
- Completion recovery now prioritizes provider/runtime replay blockers before generic artifact-proof repair.
- Added a pass-2 fixture for COMPASS-style state handoff plus generic zhengxi skill workflow evidence with no provider
  sample, asserting bounded lanes, no runtime launch, and replayable provider-runtime recovery.

## Validation

- `pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass_requires_replay_sample or provider_runtime_control_pass_continues_with_ready_sample"`
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or provider_runtime_recovery_summary"`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_harness_eval.py -q`
- `pytest -q`

Final full-suite result: `524 passed`.

## Review Notes

- No provider was launched.
- No upstream skill or harness code was installed, cloned, enabled, or executed.
- Raw evidence URLs and raw provider/runtime inputs remain omitted from structured outputs.
- The self-model was read and left unchanged; it already matched this run's preference for rollback-backed, locally
  validated behavior changes over validation-report-only work.
