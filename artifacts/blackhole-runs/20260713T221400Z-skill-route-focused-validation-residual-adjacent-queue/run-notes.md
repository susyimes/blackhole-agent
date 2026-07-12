# Run notes: skill-route focused validation residual adjacent queue

- UTC: 20260713T221400Z
- Digest: github-growth-20260712T221308.618244Z
- Proposal: prop-skill-reverse-flow-continue-local-validation
- Improvement: skill_route_discovery_focused_validation_residual_adjacent_queue
- Branch: grok/blackhole-evolve/20260712T221354.968796-advance-skill-route-discovery-for-reverse-flow-s
- Rollback: refs/blackhole-agent/rollback/20260713T221400Z-skill-route-focused-validation-residual-adjacent-queue
- HEAD at run start: 85ec4dff700b00054d7bc708bc29d1523a5e9ad6
- Working tree HEAD: 85ec4dff700b00054d7bc708bc29d1523a5e9ad6

## Hypothesis

After reverse-flow focused local test validation is recorded and activation-external
acceptance is accepted, residual fortress/Hy3 rows only left a boolean flag and a
supervisor_next string. There was no operator-visible package that queues those
residual proposal IDs for agent_harness_eval_cluster_local_apply while reverse-flow
remains the selected step and activation stays external. The selected-step adjacent
handoff only fires when the selected pipeline step is itself an adjacent harness-eval
row.

## Change set

- build_skill_route_discovery_focused_validation_residual_adjacent_queue
- Pipeline field focused_validation_residual_adjacent_queue
- record/close helpers refresh residual queue after focused validation outcomes
- Render path surfaces residual queue status/decision and prefers its supervisor next action when ready/blocked
- Docs: architecture, skill-route-discovery, self-model
- Tests: focused validation residual queue + docs contracts

## Validation

- pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation (and unlocked/pipeline/residual): 8 passed
- pytest tests/test_docs_contracts.py -q -k skill_route: 24 passed

## Review notes

- Activation remains external; no push/promotion/restart from this surface
- Residual fortress/Hy3 adjacent rows queue without skill unlock inheritance
- agent-chief-style privacy rows remain review-only
- rnskill stays documentation companion on the shared pipeline
- Distinct from skill_route_discovery_adjacent_harness_eval_handoff (selected-step only)
- Failed or unrecorded focused validation keeps residual queue blocked until acceptance
