# Run notes: skill-route focused validation activation-external handoff

- UTC: 20260712T213447Z
- Digest: github-growth-20260712T213308.729900Z
- Proposal: prop-skill-reverse-flow-focused-test-validation
- Improvement: skill_route_discovery_focused_validation_activation_external_handoff
- Branch: grok/blackhole-evolve/20260712T213357.525070-advance-reverse-flow-skill-route-discovery-throu
- Rollback: refs/blackhole-agent/rollback/20260712T213447Z-a1bae44
- HEAD at rollback: a1bae442b64a16a09549b80aa29b338db67ea8b7

## Hypothesis

After reverse-flow focused local test validation records body-free command-hash
results as `passed`, supervisors only saw a string next action
(`keep_activation_external_after_focused_local_test_validation`). Packaging that
decision into an operator-visible handoff closes the recorded-validation path
while keeping activation, push, promotion, provider launch, remote apply,
external skill execution, and kernel restart denied.

## Change set

- `build_skill_route_discovery_focused_validation_activation_external_handoff`
- Pipeline wiring after focused validation (+ recorded flag on pipeline)
- `record_skill_route_discovery_focused_local_test_validation_results` refreshes handoff
- Render lines for activation-external status/decision
- Docs: architecture, skill-route-discovery, self-model
- Tests: focused validation + docs contracts

## Validation

- `pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation` (and unlocked/pipeline): 8 passed
- `pytest tests/test_docs_contracts.py -q -k skill_route`: 24 passed

## Review notes

- Activation remains external; no push/promotion/restart from this surface
- Residual fortress/Hy3 adjacent rows may be noted without skill unlock inheritance
- agent-chief-style privacy rows remain review-only
- rnskill stays documentation companion on the shared pipeline
