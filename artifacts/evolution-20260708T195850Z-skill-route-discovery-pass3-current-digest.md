# Skill Route Discovery Pass 3 Current Digest

## Evidence

- Source digest: `github-growth-20260708T195850.396172Z`
- Primary proposals: `p1-skill-route-discovery-reverse-flow`, `p2-generic-skill-workflow-discovery`, `p3-agent-harness-eval-general-projects`
- Carried evidence URLs: reverse-flow-skill, rnskill, Shepherd, Hy3, and Blender/Seedance workflow-usecase repositories

## Hypothesis

The pass-3 window needs an operator-visible validation packet rather than another isolated fixture. Reverse-flow and rnskill evidence can be classified into bounded local test lanes before activation, while adjacent general-agent projects remain gated by local agent-harness evaluation.

## Change

- Reused the pass-3 activation-packet builder for digest-specific packet surfaces.
- Added `current_digest_20260708T195850_pass3_validation_packet`.
- Added a local harness fixture and direct route-map tests for the current digest.
- Documented the replay and activation denials.

## Rollback

- Rollback artifact: `artifacts/rollback/20260708T195850Z-skill-route-discovery-pass3-current-digest/rollback-point.md`
- Rollback execution remains an explicit destructive operator action.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k 20260708T195850`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k 20260708T195850`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k "20260708T183850 or 20260708T195850"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T183850 or 20260708T195850"`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`: passed, 1 test.
