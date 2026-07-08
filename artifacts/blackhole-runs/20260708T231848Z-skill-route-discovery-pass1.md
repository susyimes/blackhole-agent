# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260708T231850.689945Z`
- Branch: `codex/blackhole-evolve/20260708T231951.398296-add-local-route-discovery-fixtures-for-skill-ori`
- Rollback ref: `refs/blackhole-rollback/20260708T231848Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260708T231848Z-skill-route-discovery-pass1/rollback-point.md`

## Hypothesis

The active skill-route discovery slice should expose a replayable pass-1 lane
for the current reverse-flow/rnskill plus adjacent Shepherd, Hy3, and
Blender/Seedance workflow-usecase evidence. Skill/workflow repositories should
map only to documentation, config, test, or code_patch lanes, while adjacent
general-agent and workflow-usecase projects remain behind
`agent_harness_eval_required` before any local behavior adoption.

## Changes

- Added `current_digest_20260708T231850_pass1_validation_lane` to the proposal
  lane map.
- Added frozen local fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260708T231850_pass1_validation_lane.json`.
- Added a regression test asserting bounded skill lanes, selected item-id
  evidence references, harness-eval-only adjacent rows, and body-free output.
- Documented the new replay lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T231850`
  passed: 1 passed, 440 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T215850 or 20260708T231850"`
  passed: 2 passed, 439 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route`
  passed: 22 passed, 9 deselected.

## Review Notes

- No upstream repository was cloned, installed, or executed.
- No provider, external harness, remote execution, promotion, push, restart,
  profile write, or memory write path was enabled.
- `docs/self-model.md` was left unchanged because its current preference already
  matches this run: rollback-backed local validation is preferred, and the
  safety boundary remains external to the self-model.
