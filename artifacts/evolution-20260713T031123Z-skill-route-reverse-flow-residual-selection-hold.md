# Evolution: reverse-flow residual fortress selection hold

Digest: `github-growth-20260713T031123.591532Z`
Proposal: `prop-reverse-flow-skill-route-test` (with residual fortress adjacent)
Surface: residual stage selection export + focused validation residual hold

## Hypothesis

Render already suppressed residual selected proposal while residual work was not
residual-active, but residual stage packets still pre-selected fortress IDs
(`selected_residual_proposal_id` / `proposal_id`) while reverse-flow focused
validation was ready/unrecorded. That enabled premature fortress advertisement
to packet consumers before reverse-flow record/close and activation-external
acceptance.

## What changed

1. **Helper** `_export_residual_selected_proposal_id` — export residual selection
   only for residual-active statuses.
2. **Residual stage packets** (apply, comparison, unlocked apply, focused
   validation, residual handoff, residual acceptance) leave
   `selected_residual_proposal_id` / residual `proposal_id` empty while reverse-
   flow-waiting and set `residual_selection_held_until_residual_active=true`
   when an internal selection exists but is held.
3. **Focused validation** adds `residual_adjacent_hold_active` for ready/
   unrecorded **and** failed reverse-flow focused validation.
4. **Render** surfaces residual selection held until residual-active and notes
   packet-level selection export policy.
5. **Tests / docs / self-model** updated for residual selection hold and failed
   hold path.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k skill_route_discovery
PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

Result: **17 + 24 passed**.

While reverse-flow focused validation is unrecorded:
- supervisor_next: `run_focused_local_test_validation_then_keep_activation_external`
- residual selected proposal render: `none`
- residual apply/comparison/unlocked/focused/handoff/acceptance selected: empty
- residual_selection_held_until_residual_active: true on residual apply
- residual hold active: true

After close-with-outcome pass, residual stages become residual-active and fortress
selection exports again on residual apply.

## Rollback

`refs/blackhole-rollback/20260713T111443Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T111443Z-reverse-flow-residual-selection-hold.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- Residual packet cascade inheritance remains for residual-active stages
- rnskill companion and fortress residual harness-eval remain adjacent; fortress
  is not residual-active until reverse-flow gates clear
- Next operator step while reverse-flow focused validation is ready/unrecorded:
  run body-free focused commands then
  `record_skill_route_discovery_focused_local_test_validation_results` or
  `close_skill_route_discovery_focused_local_test_validation_with_outcome`
