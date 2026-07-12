# Evolution: skill-route focused validation activation-external acceptance

- UTC: 20260713T055500Z
- Digest: github-growth-20260712T215308.239488Z
- Proposal: prop-skill-reverse-flow-focused-test-validation
- Theme: skill-route-discovery (focused validation close → activation-external acceptance)
- Rollback: refs/blackhole-agent/rollback/20260713T055500Z-skill-route-focused-validation-activation-external-accept

## Change summary

Added operator-visible close-with-outcome and activation-external acceptance after
reverse-flow focused local test validation:

- `build_skill_route_discovery_focused_validation_body_free_command_results`
- `close_skill_route_discovery_focused_local_test_validation_with_outcome`
- `build_skill_route_discovery_focused_validation_activation_external_acceptance`
- Pipeline field `focused_validation_activation_external_acceptance`
- Record helper refreshes acceptance with focused results
- Render path surfaces acceptance status/decision and prefer its supervisor next action
- Docs + self-model updated for the new surfaces
- Tests: focused validation + docs contracts

Statuses:

- unrecorded focused validation → handoff `blocked_until_focused_validation_recorded`, acceptance `blocked_until_activation_external_handoff_ready`
- failed focused validation → handoff `blocked_until_focused_validation_repaired`, acceptance blocked
- recorded pass covering expected hashes → handoff `ready` with `package_activation_external_handoff_after_focused_validation_pass`
- ready handoff after pass → acceptance `accepted` with `accept_activation_external_package_after_focused_validation_pass`

## Validation

- pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation (and unlocked/pipeline): 8 passed
- pytest tests/test_docs_contracts.py -q -k skill_route: 24 passed

## Safety

Activation, push, promotion, provider launch, remote apply, external skill
execution, and kernel restart remain denied. Exports stay body-free (command
hashes / booleans only; no raw evidence URLs or stdout).
