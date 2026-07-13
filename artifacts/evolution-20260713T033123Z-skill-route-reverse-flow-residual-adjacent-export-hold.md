# Evolution: reverse-flow residual adjacent export hold

Digest: `github-growth-20260713T033123.572996Z`
Proposal: `prop-reverse-flow-skill-route-discovery` (with residual fortress adjacent)
Surface: reverse-flow residual adjacent ID/availability export hold

## Hypothesis

After residual selection hold, reverse-flow surfaces still pre-exported fortress
`adjacent_general_agent_proposal_ids` and `residual_adjacent_harness_eval_available=true`
while focused validation was ready/unrecorded. That enabled premature residual
advertisement before reverse-flow record/close and activation-external acceptance.

## What changed

1. **Focused validation** — while residual hold is active (ready/unrecorded or
   failed), leave `adjacent_general_agent_proposal_ids` empty and set
   `residual_adjacent_ids_held_until_recorded=true`. Recorded pass re-exports
   fortress IDs.
2. **Activation-external handoff** — export residual adjacent IDs/availability
   only when `status==ready`; blocked handoff sets
   `residual_adjacent_export_held_until_ready=true`.
3. **Activation-external acceptance** — export residual adjacent IDs/availability
   only when `status==accepted`.
4. **Residual queue** — `residual_adjacent_harness_eval_available` only when
   residual-active ready; held flag while reverse-flow-waiting. Internal residual
   existence no longer trusts blocked acceptance export=false as absence.
5. **Residual apply/comparison/unlocked** — residual availability tracks residual-
   active export sets only.
6. **Pipeline render** — surfaces residual adjacent export held on reverse-flow
   surfaces and documents the hold policy.
7. **Tests / docs / self-model** updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k skill_route_discovery
PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

Result: **17 + 24 passed**.

While reverse-flow focused validation is unrecorded:
- supervisor_next: `run_focused_local_test_validation_then_keep_activation_external`
- focused adjacent fortress IDs: empty
- handoff/acceptance residual_available: false
- residual queue residual_available: false
- residual apply residual_available: false
- residual selection held: true

After close-with-outcome pass + ready handoff/acceptance, residual fortress IDs
and availability re-export.

## Rollback

`refs/blackhole-rollback/20260713T113313Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T113313Z-reverse-flow-residual-adjacent-export-hold.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- rnskill companion and fortress residual harness-eval remain adjacent; fortress
  is not residual-active until reverse-flow gates clear
- Next operator step while reverse-flow focused validation is ready/unrecorded:
  run body-free focused commands then
  `record_skill_route_discovery_focused_local_test_validation_results` or
  `close_skill_route_discovery_focused_local_test_validation_with_outcome`
