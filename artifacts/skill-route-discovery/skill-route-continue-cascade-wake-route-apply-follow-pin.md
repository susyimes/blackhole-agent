# Skill route continue cascade wake route apply follow pin

Source digest: github-growth-20260714T024805.275894Z
Proposal: prop-skill-reverse-flow-continue

## Surface

`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin`

Body-free line example:

```
continue_cascade_wake_route_apply_follow_pin action=execute_now mode=execute_helper call_execute=true pin_ready=true advanced=false executed=false recorded=false residual_route=false reverse=0/3→0/3 residual=0/8→0/8 residual_export=false next=run_focused_local_test_validation_then_keep_activation_external helper=follow_reverse_flow_focused_validation_continue_dispatch follow_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow
```

## Pin modes

| Mode | When | call_execute |
| --- | --- | --- |
| `execute_helper` | `execute_now` / `record_remaining` with follow call_execute | true |
| `package_helper` | `keep_activation_external` / residual open / residual cascade / repair | false |
| `inventory_only` | no preferred helper call beyond inventory | false |

## Integration

- follow_reverse_flow_focused_validation_continue_dispatch attaches apply_follow_pin after apply_follow
- dispatch_reverse_flow_focused_validation_continue_supervisor_wake packages apply_follow_pin on execute and inventory paths
- operator_state exports nested apply_follow_pin fields for ready/unrecorded and post-pass snapshots
- residual_export stays denied; activation remains external
