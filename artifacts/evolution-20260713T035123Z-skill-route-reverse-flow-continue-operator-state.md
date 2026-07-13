# Evolution: reverse-flow continue operator-state

Digest: `github-growth-20260713T035123.555299Z`
Proposal: `prop-reverse-flow-skill-route-discovery` (with residual fortress adjacent)
Surface: durable reverse-flow continue operator_state on skill-route pipeline

## Hypothesis

After residual export hold, reverse-flow continue still depended on markdown
render to know supervisor_next and whether residual fortress IDs/export were held.
Record/close refreshed stage packets but left no durable top-level continue fields.

## What changed

1. **resolve_skill_route_discovery_pipeline_operator_state** — shared resolver for
   supervisor_next priority, residual hold/export flags, residual selected id
   (empty while reverse-flow-waiting), reverse_flow_continue_decision, and
   record helpers.
2. **attach_skill_route_discovery_pipeline_operator_state** — attaches top-level
   fields plus nested `operator_state` onto the pipeline packet.
3. **Pipeline build** and reverse-flow/residual **record/close** attach operator
   state after stage refresh.
4. **Render** uses the resolver and surfaces `Reverse-flow continue decision`.
5. While ready/unrecorded:
   `reverse_flow_continue_decision=record_or_close_reverse_flow_focused_validation_before_residual_export`
   and residual fortress export/selection stay held.
6. After close-with-outcome pass, operator_state advances to residual-active next
   and releases residual holds.
7. Tests / docs / self-model updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k skill_route_discovery
PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

Result: **17 + 24 passed**.

## Rollback

`refs/blackhole-rollback/20260713T115322Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T115322Z-reverse-flow-continue-operator-state.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- rnskill companion and fortress residual harness-eval remain adjacent; fortress
  is not residual-active until reverse-flow record/close clears holds
- Next operator step while reverse-flow focused validation is ready/unrecorded:
  run body-free focused commands then
  `record_skill_route_discovery_focused_local_test_validation_results` or
  `close_skill_route_discovery_focused_local_test_validation_with_outcome`
