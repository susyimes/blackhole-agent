# Skill Route Discovery Pass 2 Current Window

Run timestamp: 20260708T090633Z
Source digest: github-growth-20260708T090635.452817Z
Rollback ref: refs/blackhole-rollback/20260708T090633Z
Rollback artifact: artifacts/rollback/20260708T090633Z-rollback.md

## Hypothesis

The active pass-2 skill-route-discovery window should expose a replayable local
lane for reverse-flow/rnskill evidence instead of leaving the current digest to
older generic route surfaces. Reverse-flow evidence should prove
`skill_route_discovery_first` before any workflow activation, rnskill should map
to `generic_skill_workflow`, and Shepherd, Hy3, and workflow-usecase projects
should remain `agent_harness_eval_required` with no direct implementation lane.

## Change

- Added `skill_route_discovery_current_digest_20260708T090635_pass2_validation_lane`.
- Added a body-free fixture for the current digest window.
- Added regression coverage for selected lanes, proposal IDs, retained
  validation packet readiness, adjacent agent-harness queueing, rollback ref,
  and activation denials.
- Documented the replay lane in `docs/skill-route-discovery.md`.

## Validation

Run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T090635
```

Result: passed, 1 test.

## Review Notes

- Self-model was read and left unchanged. The current text already prefers
  rollback-backed local behavior changes over ornamental validation reports.
- Evidence was taken from the source digest/proposal URLs and encoded as
  selected item IDs and body-free summaries only.
- No upstream repository code is installed, cloned, executed, enabled, or
  activated by this lane.
