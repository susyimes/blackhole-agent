# Evolution: reverse-flow continue residual follow

- Source digest: `github-growth-20260713T125418.632802Z`
- Branch: `grok/blackhole-evolve/20260713T125452.388884-continue-reverse-flow-skill-route-discovery-run-`
- Proposal: `prop-reverse-flow-skill-route-discovery-continue`
- Evidence: https://github.com/lingbol088-spec/reverse-flow-skill
- Rollback ref: `refs/blackhole/rollback/20260713T125652Z`
- Rollback artifact: `artifacts/rollback/rollback-20260713T125652Z.md`

## Hypothesis

Supervisors already had residual entry cards (`residual_entry ready=true
selected=prop-harness-fortress-local-eval
next=run_agent_harness_eval_local_comparison_for_residual_adjacent_row`), but
still re-derived whether to open residual harness-eval local comparison vs wait
for residual entry vs wait for reverse-flow by reading nested residual_entry /
residual_open fields. A body-free residual follow card
(`residual_follow ready=true selected=prop-harness-fortress-local-eval
action=open_residual_harness_eval_local_comparison call_comparison=true
residual_export=false
next=run_agent_harness_eval_local_comparison_for_residual_adjacent_row
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`)
makes residual comparison follow-through legible without nested re-assembly,
while residual export stays denied on continue surfaces and
`call_residual_comparison` remains informational policy only.

## Change

- Added `package_reverse_flow_focused_validation_continue_residual_follow`
- Follow and dispatch attach `residual_follow`, `residual_follow_line`,
  `residual_follow_ready`, `residual_follow_action`, and
  `call_residual_comparison`
- Inventory-only wakes package a blocked residual follow
  (`ready=false`, `action=wait_for_reverse_flow`, `call_comparison=false`) for
  pre-exec audit
- Durable `operator_state` exports nested `continue_residual_follow`,
  `continue_residual_follow_helper`, `continue_residual_follow_line`,
  `continue_residual_follow_ready`, `continue_residual_follow_action`, and
  `continue_call_residual_comparison`
- Updated architecture, skill-route docs, self-model, and focused tests

## Validation

```
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation or skill_route_discovery_capability_pipeline"
# 7 passed

pytest tests/test_docs_contracts.py -q -k "skill_route"
# 24 passed
```

## Safety

- Residual export denied on residual follow / residual entry / residual open /
  finish / dispatch / follow
- `call_residual_comparison` is informational only; residual stages open via
  residual pipeline helpers, not residual_export on continue surfaces
- Selected residual IDs held empty while residual entry is blocked
  (reverse-flow-waiting selection hold)
- No activation, push, promotion, provider launch, remote apply, external skill
  execution, or kernel restart
- Body-free only (proposal IDs / counts / status / policy action; no raw
  evidence URLs, upstream bodies, or command stdout)

## Self-model

Updated Skill Route Discovery Habit for digest
`github-growth-20260713T125418.632802Z` to record residual follow packaging after
residual entry, grounded in this run's reverse-flow continue residual-comparison
follow-through gap.

## Review notes

- Residual fortress/Hy3 stages remain held until reverse-flow focused validation
  is recorded/closed and activation-external acceptance completes
- agent-chief remains privacy review-only
- rnskill docs companion stays subordinate while reverse-flow continue is primary
- Residual follow packages residual comparison policy after residual entry;
  supervisors still call `follow_reverse_flow_focused_validation_continue_dispatch`
  when `call_dispatch_with_execute` is true to advance 0/N → N/N before residual
  open, residual entry, and residual follow are ready
- After residual follow is ready, residual stages still advance via residual
  pipeline helpers (`build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`
  then residual unlocked apply) rather than residual_export on continue surfaces
