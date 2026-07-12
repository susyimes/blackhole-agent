# Evolution: skill-route focused validation activation-external handoff

- UTC: 20260712T213447Z
- Digest: github-growth-20260712T213308.729900Z
- Proposal: prop-skill-reverse-flow-focused-test-validation
- Theme: skill-route-discovery (post-unlock focused validation → activation-external)
- Rollback: refs/blackhole-agent/rollback/20260712T213447Z-a1bae44

## Change summary

Added operator-visible activation-external handoff after reverse-flow focused
local test validation records body-free command-hash results:

- `build_skill_route_discovery_focused_validation_activation_external_handoff`
- Pipeline field `focused_validation_activation_external_handoff`
- Pipeline field `focused_local_test_validation_recorded`
- Record helper refreshes activation-external handoff with focused results
- Render path surfaces handoff status/decision and prefer its supervisor next action
- Docs + self-model updated for the new surface

Statuses:

- unrecorded focused validation → `blocked_until_focused_validation_recorded`
- failed focused validation → `blocked_until_focused_validation_repaired`
- recorded pass covering expected hashes → `ready` with
  `package_activation_external_handoff_after_focused_validation_pass`

## Validation

- pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation (and unlocked/pipeline): 8 passed
- pytest tests/test_docs_contracts.py -q -k skill_route: 24 passed

## Safety

Activation, push, promotion, provider launch, remote apply, external skill
execution, and kernel restart remain denied. Exports stay body-free (command
hashes / booleans only; no raw evidence URLs or stdout).
