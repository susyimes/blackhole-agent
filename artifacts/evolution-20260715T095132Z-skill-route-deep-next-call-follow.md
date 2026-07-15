# Evolution: skill-route deep next_call_follow

## Hypothesis
After deep `pin_call_next_call` packaging, supervisors still re-mapped
`applied_next_action` / `applied_next_invoke` / `post_call_next_with_execute`
into which helper to call next. A body-free follow receipt removes that nested
re-derivation for the second-cycle next-call surface.

## Change
Added body-free deep next-call follow:
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call_follow`

Wired into:
- `follow_reverse_flow_focused_validation_continue_dispatch`
- execute and inventory paths of
  `dispatch_reverse_flow_focused_validation_continue_supervisor_wake`
- `resolve_skill_route_discovery_pipeline_operator_state`
- render helper bullets / operator-state lines
- architecture + skill-route docs contracts
- focused package/operator_state tests
- self-model (this digest)

## Validation
- Focused pytest: 34 passed (continue_cascade / pin_call_next / docs_contract)
- Broader github_growth + docs_contracts: 151 passed; 1 unrelated pre-existing fail (`test_github_growth_help` ANSI help output)
- residual_export_allowed=false
- runtime_action=none

## Review notes
- agent-chief remains review-only for privacy leakage risk
- Hy3 / fortress residual rows stay held until reverse-flow record/close and
  activation-external acceptance
- Activation, push, promotion, and kernel restart remain external supervisor concerns
- Rollback: `artifacts/blackhole-runs/rollback-20260715T175324Z.md`
