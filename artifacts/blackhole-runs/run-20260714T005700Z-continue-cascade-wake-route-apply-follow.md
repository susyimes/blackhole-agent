# Evolution Run Summary

- Digest: github-growth-20260714T005419.520584Z
- Proposal: prop-skill-reverse-flow-continue
- Branch: grok/blackhole-evolve/20260714T005509.459604-continue-reverse-flow-skill-route-discovery-agai
- Rollback: artifacts/rollback/20260714T005559Z-continue-cascade-wake-route-apply-follow.md
- Rollback ref: refs/blackhole/rollback/20260714T005559Z

## Hypothesis

After continue cascade wake route apply collapses pre/post routes into one apply
receipt, supervisors still re-mapped applied_route_action to preferred helper and
call_execute by inspecting nested post-route fields. A body-free apply-follow
receipt should pin that policy so reverse-flow continue wakes stay legible.

## Change

Added package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow
and wired it through follow/dispatch/operator_state/render/docs/tests.

## Validation

- pytest tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply -q → 1 passed
- pytest tests/test_docs_contracts.py -q → 34 passed

## Safety

- residual_export denied on apply-follow surface
- activation/push/promotion/restart remain external
- no raw evidence URLs, bodies, or command stdout exported
