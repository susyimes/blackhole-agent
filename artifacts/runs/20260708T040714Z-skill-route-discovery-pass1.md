# Skill Route Discovery Pass 1

Source digest: github-growth-20260708T040637.530560Z
Branch: codex/blackhole-evolve/20260708T040714.289466-run-a-bounded-local-skill-route-discovery-lane-f
Rollback point: artifacts/rollback/20260708T040714Z-skill-route-discovery-pass1/rollback-point.md

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/Pluviobyte/rnskill
- https://github.com/shepherd-agents/shepherd

## Hypothesis

The current skill-route window should be replayable as a bounded local lane before activation:
reverse-flow-skill maps to a Codex workflow test lane, rnskill maps to a generic skill workflow documentation lane, and Shepherd remains behind agent_harness_eval_required.

## Local Changes

- Added current digest recognition for `github-growth-20260708T040637.530560Z` in the pass-1 skill-route validation lane and activation-readiness panel.
- Added an offline local harness fixture for this digest.
- Added focused route-map and harness regression tests.
- Updated aggregate local harness fixture counts for the added passing fixture.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T040637`
- `python -m pytest tests/test_harness_eval.py -q -k 20260708T040637`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T172109 or 20260708T040637"`

All validation commands passed.

## Review Notes

- No external repository code was cloned, installed, or executed.
- Raw evidence URLs and replay commands remain excluded from exported route packets.
- Shepherd is represented only as an adjacent general-agent project requiring local harness evaluation.
- `docs/self-model.md` was read and left unchanged because its current preference already matches this rollback-backed, locally validated behavior experiment.
