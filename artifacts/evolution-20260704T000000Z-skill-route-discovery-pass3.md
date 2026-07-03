# Evolution Run: skill-route-discovery pass 3

- Source digest: `github-growth-20260703T232924.872543Z`
- Rollback artifact: `artifacts/rollback-20260704T000000Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/blackhole-rollback/20260704T000000Z`
- Branch: `codex/blackhole-evolve/20260703T233021.965963-add-or-extend-local-tests-for-codex-oriented-ski`

## Hypothesis

The current pass 3 skill-route discovery window needs an operator-visible replay lane, not just another
standalone fixture. A digest-facing lane should convert Codex skill workflow evidence, generic skill workflow
evidence, and adjacent general-agent evidence into bounded local validation rows before activation.

## Change

Added `current_pass3_skill_route_replay_lane` to the proposal route-hint lane map. The lane records the active
proposal IDs, selected item IDs, bounded skill-route lanes, adjacent `agent_harness_eval_required` rows, hashed
local replay commands, and denied runtime/export actions.

## Evidence Handling

Primary evidence stayed within the provided proposal URLs and frozen digest descriptions. No broad trend
discovery was rerun. The operator lane is body-free and does not export raw upstream URLs, upstream bodies, or
raw replay commands.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k current_pass3_skill_route_replay_lane`
- `python -m pytest tests/test_proposal_eval.py -q -k "current_pass3 or route_hint_lane_map"`
- `python -m pytest tests/test_github_growth.py -q -k current_pass3_route_readiness_index`
- `python -m pytest tests/test_proposal_eval.py -q`

All listed validation commands passed during this run.

## Review Notes

- General agent project rows remain blocked behind `agent_harness_eval` and do not inherit `skill_route_discovery`.
- The lane exposes command hashes only; operators must use local validation policy to choose exact replay commands.
- Self-model was read and left unchanged because it already matches the validation-backed local evolution boundary used here.
