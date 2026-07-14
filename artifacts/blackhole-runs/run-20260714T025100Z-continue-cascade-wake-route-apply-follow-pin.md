# Run: continue cascade wake route apply follow pin

- Source digest: `github-growth-20260714T024805.275894Z`
- Proposal: `prop-skill-reverse-flow-continue`
- Branch: `grok/blackhole-evolve/20260714T024911.720982-continue-reverse-flow-skill-route-discovery-run-`
- Rollback ref: `refs/blackhole/rollback/20260714T025055Z-continue-cascade-wake-route-apply-follow-pin`
- Rollback HEAD: `49f614c410f9fab96b4a38e17e95b7000b405158`

## Hypothesis

After apply_follow maps applied route → preferred helper, supervisors still
re-derived whether to call that helper with execute vs package-only vs inventory
by combining nested follow fields. A body-free pin surface collapses follow
policy into one call recipe (`execute_helper` / `package_helper` /
`inventory_only`) so reverse-flow continue wakes stay legible without nested
re-assembly, while residual_export and activation stay denied.

## Change set

- `package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin`
- Wired into follow/dispatch inventory + execute paths
- operator_state + render exports for pin line/action/mode/helper/call_execute/ready
- Tests, skill-route docs, architecture, self-model, run artifacts

## Safety

- residual_export_allowed = false on pin surface
- runtime_action = none
- no activation / push / promotion / provider launch / remote apply / external skill / restart
- no raw evidence URLs, bodies, or command stdout

## Validation

```
pytest tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply -q
# 1 passed

pytest tests/test_github_growth.py -q -k skill_route_discovery
# 17 passed, 101 deselected

pytest tests/test_docs_contracts.py -q -k skill_route
# 24 passed, 10 deselected
```

Result: pass. residual_export remains denied on pin surface; activation external only.
