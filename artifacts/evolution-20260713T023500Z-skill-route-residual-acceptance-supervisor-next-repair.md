# Evolution: residual acceptance supervisor_next repair

Digest: `github-growth-20260713T023123.638634Z`
Proposal: `prop-reverse-flow-skill-route-test` (with residual fortress adjacent)
Surface: `skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`
Related: `repair_skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`

## Hypothesis

While reverse-flow focused local test validation is `ready` but unrecorded,
residual stages correctly stay blocked. Residual activation-external acceptance
still emitted
`repair_skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`
for any residual handoff status starting with `blocked`, and pipeline render
priority promoted that residual acceptance next action over reverse-flow focused
validation. Operators/kernels therefore saw a residual-handoff "repair" signal
instead of
`run_focused_local_test_validation_then_keep_activation_external`.

## What changed

1. **Residual acceptance builder**
   (`build_skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`):
   when residual handoff is blocked, inherit handoff's cascaded
   `supervisor_next_action` first. Only isolation failures (`blocked`) without a
   handoff next action still emit residual-handoff repair.

2. **Pipeline render prioritization**
   (`render_skill_route_discovery_capability_pipeline_lines`): residual acceptance
   owns operator-visible supervisor_next only when accepted, or when residual
   handoff is residual-active (`ready`, recorded/repaired/pass blocked, isolation
   `blocked`). Mere
   `blocked_until_residual_adjacent_focused_validation_ready` no longer lets
   residual acceptance override earlier reverse-flow stages.

3. **Tests** cover inheritance, premature residual acceptance, and rendered
   supervisor_next while reverse-flow focused validation is unrecorded.

4. **Docs / self-model** record the cascade and prioritization rule.

## Validation

```
PYTHONPATH=src python -m pytest \
  tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply \
  tests/test_docs_contracts.py -q
```

Result: **35 passed**.

Reproduced pre-fix supervisor_next:
`repair_skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`

Post-fix supervisor_next:
`run_focused_local_test_validation_then_keep_activation_external`

## Rollback

`refs/blackhole-rollback/20260713T103337Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T103337Z-residual-acceptance-supervisor-next.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- Residual acceptance still inherits failed residual focused repair when residual
  handoff is `blocked_until_residual_adjacent_focused_validation_repaired`
- Isolation failures on residual handoff itself may still surface residual-handoff
  repair; that is intentional
- True residual work remains the next step only after reverse-flow focused
  validation is recorded and residual stages become residual-active
