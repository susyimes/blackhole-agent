# Evolution: skill-route continue cascade pin_call_next_call_follow

## Hypothesis
After deep pin_call_next_call receipts sealed pre→post next-invoke transitions,
supervisors still re-mapped `applied_next_action`, `applied_next_invoke`,
`post_call_next_with_execute`, and residual-route flags into which helper to call
next after continue wakes.

## Change
Added body-free deep next-call follow seal:
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow`

Maps deep next_call receipts into
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_line`
with classified follow policy (`execute_helper` / `package_helper` /
`inventory_only`).

Wired into:
- `follow_reverse_flow_focused_validation_continue_dispatch`
- execute and inventory paths of
  `dispatch_reverse_flow_focused_validation_continue_supervisor_wake`
- durable `operator_state` + render lines
- architecture / skill-route-discovery docs
- self-model (digest `github-growth-20260715T045131.487927Z`)
- focused package + operator_state tests
- docs contracts helper inventory

## Validation
- pytest focused suite (`skill_route|reverse_flow|pin_call|continue_cascade|docs_contract`): 61 passed
- residual_export_allowed=false
- runtime_action=none

## Review notes
- agent-chief remains review-only for privacy leakage risk
- Hy3 / fortress residual rows stay held until reverse-flow record/close and
  activation-external acceptance
- Activation, push, promotion, and kernel restart remain external supervisor concerns
- Rollback point: `artifacts/rollback-20260715T125350Z.md`
  (`refs/blackhole-rollback/20260715T125350Z`)
