# Evolution: reverse-flow continue residual comparison

- Source digest: `github-growth-20260713T135419.207508Z`
- Branch: `grok/blackhole-evolve/20260713T135505.321471-continue-skill-route-discovery-for-reverse-flow-`
- Proposal: `prop-reverse-flow-skill-route-discovery-continue`
- Evidence: https://github.com/lingbol088-spec/reverse-flow-skill
- Rollback ref: `refs/blackhole/rollback/20260713T135716Z`
- Rollback artifact: `artifacts/rollback/rollback-20260713T135716Z.md`

## Hypothesis

Supervisors already had residual follow cards (`residual_follow ready=true
selected=prop-harness-fortress-local-eval
action=open_residual_harness_eval_local_comparison call_comparison=true`), but
still re-derived residual comparison status, unlocked lanes, and post-comparison
next action by calling
`build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`
and reading nested residual apply / comparison fields. A body-free residual
comparison card
(`residual_comparison ready=true selected=prop-harness-fortress-local-eval
status=ready comparison=passed_local_comparison unlocked=documentation,test,code_patch
action=open_residual_unlocked_local_lane_apply call_unlocked_apply=true
residual_export=false
next=apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`)
makes residual comparison readiness and unlocked-lane policy legible without
nested re-assembly, while residual export stays denied on continue surfaces and
`call_residual_unlocked_apply` remains informational policy only.

## Change

- Added `package_reverse_flow_focused_validation_continue_residual_comparison`
- Follow and dispatch attach `residual_comparison`, `residual_comparison_line`,
  `residual_comparison_ready`, `residual_comparison_action`, and
  `call_residual_unlocked_apply`
- Inventory-only wakes package a blocked residual comparison
  (`ready=false`, `action=wait_for_reverse_flow`, `call_unlocked_apply=false`) for
  pre-exec audit
- Durable `operator_state` exports nested `continue_residual_comparison`,
  `continue_residual_comparison_helper`, `continue_residual_comparison_line`,
  `continue_residual_comparison_ready`, `continue_residual_comparison_action`,
  and `continue_call_residual_unlocked_apply`
- Updated architecture, skill-route docs, self-model, and focused tests

## Validation

```
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation or skill_route_discovery_capability_pipeline"
# 7 passed, 111 deselected

pytest tests/test_docs_contracts.py -q -k "skill_route"
# 24 passed, 10 deselected
```

## Safety

- Residual export denied on residual comparison / residual follow / residual
  entry / residual open / finish / dispatch / follow
- `call_residual_unlocked_apply` is informational only; residual stages open via
  residual pipeline helpers, not residual_export on continue surfaces
- Selected residual IDs held empty while residual follow is blocked
  (reverse-flow-waiting selection hold)
- No activation, push, promotion, provider launch, remote apply, external skill
  execution, or kernel restart
- Body-free only (proposal IDs / counts / status / unlocked lane names / policy
  action; no raw evidence URLs, upstream bodies, or command stdout)

## Self-model

Updated Skill Route Discovery Habit for digest
`github-growth-20260713T135419.207508Z` to record residual comparison packaging
after residual follow, grounded in this run's reverse-flow continue residual
comparison readiness gap.

## Review notes

- Residual fortress/Hy3 stages remain held until reverse-flow focused validation
  is recorded/closed and activation-external acceptance completes
- agent-chief remains privacy review-only
- rnskill docs companion stays subordinate while reverse-flow continue is primary
- Residual comparison packages unlocked-lane readiness after residual follow;
  supervisors still call `follow_reverse_flow_focused_validation_continue_dispatch`
  when `call_dispatch_with_execute` is true to advance 0/N → N/N before residual
  open, residual entry, residual follow, and residual comparison are ready
- After residual comparison is ready, residual stages still advance via residual
  pipeline helpers (`build_skill_route_discovery_residual_adjacent_unlocked_local_lane_apply`
  then residual focused validation) rather than residual_export on continue surfaces
