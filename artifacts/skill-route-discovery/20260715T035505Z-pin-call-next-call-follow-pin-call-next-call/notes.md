# pin_call_next_call (deep tip)

## Evidence
- Primary proposal prop-skill-reverse-flow-continue against lingbol088-spec/reverse-flow-skill
- Capability theme skill-route-discovery; branch run-skill-route-discovery-against-pluviobyte-rns
- Prior tip sealed pin_call → next-invoke recipe; this run collapses pre/post next recipes into a next-call receipt

## Behavior
- New helper: package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call
- Identity: action=execute_now→execute_now invoke=execute_helper→execute_helper next_advanced=false residual_export=false
- Advanced: action=execute_now→keep_activation_external invoke=execute_helper→package_helper next_advanced=true
- Residual open: action=keep_activation_external→open_residual_entry residual_route=false→true residual_export=false
- Wired into follow, dispatch execute, inventory, operator_state, render lines, architecture/skill-route docs, self-model

## Safety
- residual_export_allowed=false
- runtime_action=none
- activation/push/promotion/provider/remote/external-skill/restart denied
- No raw URL/body/stdout export

## Validation
- PYTHONPATH=worktree/src
- pytest pin_call_next/skill_route/docs subset: 59 passed
- pytest focused pipeline + docs contracts: 37 passed
- Unrelated pre-existing: test_github_growth_help may fail on ANSI CLI help formatting (not introduced by this change)
