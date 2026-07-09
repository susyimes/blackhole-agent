# Skill Route Discovery Pass 2 Validation Gate

- Source digest: `github-growth-20260709T035527.234626Z`
- Theme: `skill-route-discovery`
- Proposal focus: `p1-skill-route-discovery-gate`, `p2-skill-route-discovery-docs`
- Rollback point: `refs/rollback/20260709T035611Z-skill-route-discovery-pass2-bounded-lanes`

## Evidence

Reviewed the carried public evidence URLs only:

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/Pluviobyte/rnskill`

Reusable lesson: public skill repositories can expose useful route evidence
while also advertising install, runtime, plugin-marketplace, or script pressure.
The local controller should convert those signals into bounded validation lanes
before any implementation handoff.

## Hypothesis

`validation_lane_gate` should be operator-visible at row level, not only as a
summary count. For each skill-route proposal it should show whether the lane is
bounded, local validation is required, validation commands are present, and
activation remains non-executable, while exporting hashes and counts instead of
raw source URLs or upstream bodies.

## Change

- Extended `skill_route_discovery_validation_lane_gate` with body-free per-lane
  rows.
- Added a current pass-2 regression that routes `reverse-flow-skill` and
  `rnskill` only into documentation, config, test, and code_patch lanes while
  keeping adjacent Hy3/workflow-usecase items behind agent-harness evaluation.
- Updated the route-discovery documentation to describe row-level gate
  interpretation.

## Validation

Local checks:

- Passed: `python -m pytest tests/test_harness_eval.py -q -k "20260709T035527 or skill_route_discovery_lane_fixture_bounds_evidence_before_activation"`
  (`2 passed, 265 deselected`)
- Passed: `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
  (`11 passed, 256 deselected`)

## Review Notes

The self-model was read and left unchanged. Its current preference for
rollback-backed, locally validated evolution already matches this pass. Adjacent
general-agent/workflow evidence remains non-activating and must pass
`agent_harness_eval_required` before it can produce documentation, test, or
code_patch follow-up.
