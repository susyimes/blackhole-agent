# Run notes: skill-route focused validation activation-external acceptance

- UTC: 20260713T055500Z
- Digest: github-growth-20260712T215308.239488Z
- Proposal: prop-skill-reverse-flow-focused-test-validation
- Improvement: close_skill_route_discovery_focused_local_test_validation_with_outcome + skill_route_discovery_focused_validation_activation_external_acceptance
- Branch: grok/blackhole-evolve/20260712T215347.603815-advance-reverse-flow-skill-under-skill-route-dis
- Rollback: refs/blackhole-agent/rollback/20260713T055500Z-skill-route-focused-validation-activation-external-accept
- HEAD at rollback: 0159a1ec5b9e371e643dfd12b5c02c7d76632b2a

## Hypothesis

After reverse-flow focused local test validation is ready, supervisors still had
to re-list command hashes to record results, and a ready activation-external
handoff had no terminal acceptance package. Materializing body-free expected-hash
outcomes and accepting the activation-external handoff closes the reverse-flow
focused-validation slice while push, promotion, provider launch, remote apply,
external skill execution, and kernel restart stay denied.

## Change set

- `build_skill_route_discovery_focused_validation_body_free_command_results`
- `close_skill_route_discovery_focused_local_test_validation_with_outcome`
- `build_skill_route_discovery_focused_validation_activation_external_acceptance`
- Pipeline field `focused_validation_activation_external_acceptance`
- Record helper refreshes acceptance with focused results
- Render path surfaces acceptance status/decision and prefers its supervisor next action
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
- Failed focused validation keeps acceptance blocked until repair
