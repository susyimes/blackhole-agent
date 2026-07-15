# Skill route discovery — deep next-call follow pin

- Digest: `github-growth-20260715T105131.632764Z`
- Proposal: `prop-rnskill-skill-route-discovery-continue`
- Theme: skill-route-discovery (pass 4/4 complete; reverse-flow focused validation operator-first)
- Hypothesis: After deep next_call is mapped to a follow receipt, supervisors still re-derive execute vs package pin policy from nested follow fields. Packaging a body-free deeper pin recipe reduces operator re-assembly without enabling residual export or activation.

## Change

Added `package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin`:

- Maps deeper next_call_follow → pin_action / pin_mode / call_pin_with_execute / pin_ready
- Body-free line surface with residual_export=false
- Wired into follow dispatch, supervisor wake dispatch (execute + inventory), and operator_state export
- Docs + tests + self-model updated for this layer

## Safety

- residual_export denied on continue surfaces
- activation/push/promotion/provider launch/remote apply/external skill/kernel restart stay denied
- agent-chief remains privacy review-only
- fortress/Hy3 residual stages stay held until reverse-flow activation-external acceptance

## Rollback

- Ref: `refs/blackhole/rollback/20260715T105333Z`
- Artifact: `artifacts/self-evolution/rollback-20260715T105333Z.md`
