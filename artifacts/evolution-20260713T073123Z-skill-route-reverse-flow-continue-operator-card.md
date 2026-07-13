# Evolution: reverse-flow continue operator card

- Source digest: `github-growth-20260713T073123.781342Z`
- Branch: `grok/blackhole-evolve/20260713T073232.159903-continue-skill-route-discovery-against-reverse-f`
- Proposal: `prop-reverse-flow-skill-route-discovery-continue`
- Evidence: https://github.com/lingbol088-spec/reverse-flow-skill
- Rollback ref: `refs/blackhole/rollback/20260713T153325Z`
- Rollback artifact: `artifacts/rollback/rollback-20260713T153325Z.md`

## Hypothesis

Supervisors already had inventory dispatch + follow-through policy
(`execute_now` / `call_dispatch_with_execute`), but still re-assembled reverse-flow
focused-validation progress (`0/3`), residual hold, preferred helper, and
`supervisor_next` from many nested `operator_state` fields. A single body-free
operator card makes 0/N → N/N progress and follow-through policy legible without
re-deriving nested wake fields, while residual fortress stages stay blocked until
reverse-flow record/close and activation-external acceptance.

## Change

- Added `package_reverse_flow_focused_validation_continue_operator_card`
- Attached `operator_card` / `post_operator_card` and
  `progress_label` / `post_progress_label` on follow + dispatch surfaces
- Exported nested card + `continue_progress_label` on durable `operator_state`
- Updated architecture, skill-route docs, self-model, and focused tests

## Validation

```
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation or skill_route_discovery_capability_pipeline"
# 7 passed

pytest tests/test_docs_contracts.py -q -k "skill_route"
# 24 passed
```

## Safety

- Residual export denied on operator card / dispatch / follow surfaces
- No activation, push, promotion, provider launch, remote apply, external skill
  execution, or kernel restart
- Body-free only (no raw evidence URLs, upstream bodies, or command stdout)

## Review notes

- Residual fortress/Hy3 stages remain held until reverse-flow focused validation
  is recorded/closed and activation-external acceptance completes
- agent-chief remains privacy review-only
- rnskill docs companion stays subordinate while reverse-flow continue is primary
- Operator card does not itself execute units; supervisors still call
  `follow_reverse_flow_focused_validation_continue_dispatch` when
  `call_dispatch_with_execute` is true
