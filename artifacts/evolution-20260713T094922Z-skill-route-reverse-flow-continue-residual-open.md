# Evolution: reverse-flow continue residual open

- Source digest: `github-growth-20260713T094922.242319Z`
- Branch: `grok/blackhole-evolve/20260713T095007.842990-continue-reverse-flow-skill-route-discovery-agai`
- Proposal: `prop-reverse-flow-skill-route-discovery-continue`
- Evidence: https://github.com/lingbol088-spec/reverse-flow-skill
- Rollback ref: `refs/blackhole/rollback/20260713T175144Z`
- Rollback artifact: `artifacts/rollback/rollback-20260713T175144Z.md`

## Hypothesis

Supervisors already had finish receipts (`finish complete=true residual_queue=ready`),
but still re-derived residual adjacent queue status, residual proposal ID counts,
residual next action, and residual apply helper from nested
`focused_validation_residual_adjacent_queue` fields after reverse-flow continue
finished. A body-free residual open card
(`residual_open ready=true count=1 status=ready
next=hand_off_residual_adjacent_rows_to_agent_harness_eval_cluster_local_apply
residual_export=false
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_apply`)
makes residual pipeline entry legible without nested re-assembly, while residual
export stays denied on continue surfaces themselves.

## Change

- Added `package_reverse_flow_focused_validation_continue_residual_open`
- Follow and dispatch attach `residual_open`, `residual_open_line`,
  `residual_open_ready`, and `residual_adjacent_count`
- Inventory-only wakes package a blocked residual open
  (`ready=false`, `count=0`) for pre-exec audit
- Durable `operator_state` exports nested `continue_residual_open`,
  `continue_residual_open_helper`, `continue_residual_open_line`,
  `continue_residual_open_ready`, and `continue_residual_adjacent_count`
- Updated architecture, skill-route docs, self-model, and focused tests

## Validation

```
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation or skill_route_discovery_capability_pipeline"
# 7 passed

pytest tests/test_docs_contracts.py -q -k "skill_route"
# 24 passed
```

## Safety

- Residual export denied on residual open / finish / dispatch / follow
- `residual_open_ready` is informational only; residual stages open via residual
  pipeline helpers, not residual_export on continue surfaces
- No activation, push, promotion, provider launch, remote apply, external skill
  execution, or kernel restart
- Body-free only (proposal IDs / counts / status; no raw evidence URLs, upstream
  bodies, or command stdout)

## Self-model

Updated Skill Route Discovery Habit for digest
`github-growth-20260713T094922.242319Z` to record residual open packaging after
finish receipt, grounded in this run's reverse-flow continue residual-entry gap.

## Review notes

- Residual fortress/Hy3 stages remain held until reverse-flow focused validation
  is recorded/closed and activation-external acceptance completes
- agent-chief remains privacy review-only
- rnskill docs companion stays subordinate while reverse-flow continue is primary
- Residual open packages residual entry after finish; supervisors still call
  `follow_reverse_flow_focused_validation_continue_dispatch` when
  `call_dispatch_with_execute` is true to advance 0/N → N/N before residual open
  is ready
- After residual open is ready, residual stages still advance via residual
  pipeline helpers (`build_skill_route_discovery_residual_adjacent_harness_eval_local_apply`)
  rather than residual_export on continue surfaces
