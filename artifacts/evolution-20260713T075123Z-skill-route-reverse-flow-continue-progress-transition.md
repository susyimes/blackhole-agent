# Evolution: reverse-flow continue progress transition

- Source digest: `github-growth-20260713T075123.779833Z`
- Branch: `grok/blackhole-evolve/20260713T075216.619864-continue-reverse-flow-skill-route-discovery-on-t`
- Proposal: `prop-reverse-flow-skill-route-discovery-continue`
- Evidence: https://github.com/lingbol088-spec/reverse-flow-skill
- Rollback ref: `refs/blackhole/rollback/20260713T075509Z`
- Rollback artifact: `artifacts/rollback/rollback-20260713T075509Z.md`

## Hypothesis

Supervisors already had operator cards with pre/post `progress_label` values, but
still compared nested fields to see whether a continue wake advanced `0/3` toward
`N/N`. A body-free progress transition surface (`0/3→3/3`) plus operator-card
`action_line` makes reverse-flow continue wake receipts legible without re-deriving
nested cards, while residual fortress stages stay blocked until reverse-flow
record/close and activation-external acceptance.

## Change

- Added `package_reverse_flow_focused_validation_continue_progress_transition`
- Operator card now includes body-free `action_line`
- Follow + dispatch attach `progress_transition`, `progress_transition_label`,
  `progress_advanced`, `transition_line`, `action_line`, and `post_action_line`
- Durable `operator_state` exports `continue_action_line` and
  `continue_progress_transition_helper`
- Updated architecture, skill-route docs, self-model, and focused tests

## Validation

```
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation or skill_route_discovery_capability_pipeline"
# 7 passed

pytest tests/test_docs_contracts.py -q -k "skill_route"
# 24 passed
```

## Safety

- Residual export denied on operator card / progress transition / dispatch / follow
- No activation, push, promotion, provider launch, remote apply, external skill
  execution, or kernel restart
- Body-free only (no raw evidence URLs, upstream bodies, or command stdout)

## Review notes

- Residual fortress/Hy3 stages remain held until reverse-flow focused validation
  is recorded/closed and activation-external acceptance completes
- agent-chief remains privacy review-only
- rnskill docs companion stays subordinate while reverse-flow continue is primary
- Progress transition packages wake receipts; supervisors still call
  `follow_reverse_flow_focused_validation_continue_dispatch` when
  `call_dispatch_with_execute` is true to advance 0/N → N/N
