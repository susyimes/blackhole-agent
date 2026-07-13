# Evolution: reverse-flow focused validation residual hold

Digest: `github-growth-20260713T025123.568912Z`
Proposal: `prop-reverse-flow-skill-route-test` (with residual fortress adjacent)
Surface: `skill_route_discovery_focused_local_test_validation` + pipeline render residual-active ownership

## Hypothesis

While reverse-flow focused local test validation is `ready` but unrecorded,
residual stages correctly stay blocked and cascade
`run_focused_local_test_validation_then_keep_activation_external`. The prior
residual-acceptance repair stopped residual acceptance from emitting a repair
signal, but reverse-flow-waiting residual statuses (queue
`blocked_until_activation_external_acceptance`, residual handoff
`blocked_until_residual_adjacent_focused_validation_ready`, etc.) could still
own render priority and advertise residual fortress selection before reverse-flow
focused validation was recorded/closed.

## What changed

1. **Focused validation packet**
   (`build_skill_route_discovery_focused_local_test_validation`):
   marks `residual_adjacent_hold_until_recorded` while ready/unrecorded,
   names record helpers, and names activation-external handoff after record.

2. **Pipeline render prioritization**
   (`render_skill_route_discovery_capability_pipeline_lines`): residual stages
   own operator-visible `supervisor_next` only when residual-active
   (`ready`, recorded/repaired/pass blocked, isolation `blocked`). Reverse-flow-waiting
   residual statuses no longer own priority. Residual selected proposal is
   suppressed until residual work is residual-active. Render also surfaces the
   residual hold line while reverse-flow focused validation is unrecorded.

3. **Tests** cover residual hold fields, render hold line, residual selected
   proposal suppression, and post-pass hold release.

4. **Docs / self-model** record residual hold and residual-active render rules.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py -q -k skill_route_discovery
PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q
```

Result: **17 + 34 passed**.

While reverse-flow focused validation is unrecorded:
- supervisor_next: `run_focused_local_test_validation_then_keep_activation_external`
- residual selected proposal render: `none`
- residual hold line: `True`

After close-with-outcome pass, residual hold clears and residual stages become residual-active.

## Rollback

`refs/blackhole-rollback/20260713T105347Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T105347Z-reverse-flow-focused-validation-residual-hold.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- Residual packet cascade inheritance remains for residual-active stages
- Next operator step while reverse-flow focused validation is ready/unrecorded:
  run body-free focused commands then
  `record_skill_route_discovery_focused_local_test_validation_results` or
  `close_skill_route_discovery_focused_local_test_validation_with_outcome`
