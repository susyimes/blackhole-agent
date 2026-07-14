# Evolution: continue cascade wake route apply follow pin call

- Source digest: `github-growth-20260714T034752.861616Z`
- Working branch: `grok/blackhole-evolve/20260714T034849.091635-continue-reverse-flow-skill-route-discovery-agai`
- Proposal track: `prop-skill-reverse-flow-continue` (theme: skill-route-discovery)
- Hypothesis: After pin packaging classifies execute vs package recipes, supervisors still re-derived whether a continue wake advanced the pin by comparing nested pre/post pin fields. A body-free pin_call receipt collapses pre→post pin action/mode transitions so supervisors pin one call receipt.

## Change

Added `package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call` and wired it into:

- `follow_reverse_flow_focused_validation_continue_dispatch`
- `dispatch_reverse_flow_focused_validation_continue_supervisor_wake` (execute + inventory)
- `resolve_skill_route_discovery_pipeline_operator_state`
- pipeline render lines / docs / self-model

Example body-free line after a successful reverse-flow continue wake:

`continue_cascade_wake_route_apply_follow_pin_call pre_action=execute_now post_action=keep_activation_external action=execute_now→keep_activation_external mode=execute_helper→package_helper call_execute=true→false pin_advanced=true ... residual_export=false`

Identity/inventory keeps pre_pin == post_pin with `pin_advanced=false`.

## Safety

- `runtime_action=none`
- residual export denied on pin_call surfaces
- activation / push / promotion / provider launch / remote apply / external skill / kernel restart denied
- no stdout or raw evidence URL export

## Validation

`
PYTHONPATH=src pytest tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply tests/test_github_growth.py::test_skill_route_discovery_unlocked_local_test_lane_apply_after_completion tests/test_docs_contracts.py -q
# 36 passed
`

## Self-model

Updated `docs/self-model.md` Observed section for digest `github-growth-20260714T034752.861616Z` to record pin_call as the new operator surface.

## Rollback

- Ref: `refs/blackhole/rollback/20260714T115011Z`
- Artifact: `artifacts/blackhole-runs/rollback-20260714T115011Z.md`
- HEAD at rollback: `d81ed2cccc02ee31768f0159996047644cb5e196`

## Review notes

- Residual fortress/Hy3 stages remain blocked until reverse-flow focused validation is recorded/closed (0/3) and activation-external acceptance.
- rnskill docs companion and residual harness-eval remain held behind reverse-flow continue.
- agent-chief remains privacy review-only.
- Supervisors should still run pending reverse-flow focused validation (`continue_plan.mode=run_pending`) via pin recipe `execute_helper` / preferred helper `follow_reverse_flow_focused_validation_continue_dispatch`.
