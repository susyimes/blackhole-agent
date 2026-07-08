# Skill Route Discovery Pass 3

Source digest: github-growth-20260708T044637.626170Z
Branch: codex/blackhole-evolve/20260708T044726.234402-add-or-extend-local-tests-for-skill-route-discov
Rollback point: artifacts/blackhole-runs/20260708T044635Z/rollback.md

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/Pluviobyte/rnskill
- https://github.com/shepherd-agents/shepherd
- https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases

## Hypothesis

The active pass-3 route window should be replayable as a bounded local route probe: reverse-flow skill evidence keeps the codex workflow gate visible, rnskill remains generic SKILL.md collection evidence, and adjacent runtime or workflow-usecase repositories stay behind local agent harness evaluation.

## Local Changes

- Added `github-growth-20260708T044637.626170Z` recognition to the current digest route lane and activation-readiness summary.
- Added a local harness fixture for two skill-route candidates plus Shepherd and Blender/Seedance adjacent evaluation rows.
- Added focused route-map and harness tests for bounded lanes, route profiles, route hints, and no direct adjacent implementation lanes.
- Documented the codex workflow gate versus generic skill workflow distinction.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T044637`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k 20260708T044637`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T040637 or 20260708T044637"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route`: passed, 17 tests.
- `git diff --check`: passed with line-ending warnings only.

## Review Notes

- No external repository code was cloned, installed, or executed.
- Raw upstream URLs, upstream bodies, and replay commands remain excluded from route packets.
- `docs/self-model.md` was read and left unchanged because it already matches this rollback-backed local validation change.
