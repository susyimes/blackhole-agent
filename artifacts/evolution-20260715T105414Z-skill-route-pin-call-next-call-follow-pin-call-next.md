# Evolution: skill-route continue cascade pin_call_next

## Hypothesis
Supervisors still re-derived next-invoke policy from nested pin_call transitions after pin_call_next_call_follow_pin_call packaging.

## Change
Added body-free next-invoke seal:
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next`

Wired into follow dispatch, execute/inventory dispatch paths, operator_state, render lines, architecture/skill-route docs, self-model, and focused tests.

## Validation
- pytest focused suite: 35 passed
- residual_export_allowed=false
- runtime_action=none

## Review notes
- agent-chief (11768976323-1, trend:SmileLikeYe/agent-chief-3) remains review-only for privacy leakage risk
- Hy3 residual rows stay held until reverse-flow record/close and activation-external acceptance
- Activation, push, promotion, and kernel restart remain external supervisor concerns
