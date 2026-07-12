# Run notes: skill-route residual adjacent harness-eval local apply

- UTC: 20260713T223500Z
- Digest: github-growth-20260712T223308.255959Z
- Proposal: prop-residual-adjacent-fortress-harness-eval
- Improvement: skill_route_discovery_residual_adjacent_harness_eval_local_apply
- Branch: grok/blackhole-evolve/20260712T223348.625095-continue-skill-route-discovery-for-reverse-flow-
- Rollback: refs/blackhole-agent/rollback/20260712T223459Z-residual-adjacent-harness-eval-local-apply
- HEAD at run start: ed3c3b814fd0c49f85f9abf3f34970d0c9d5e8d5
- Working tree HEAD: ed3c3b814fd0c49f85f9abf3f34970d0c9d5e8d5 (pre-commit local evolution)

## Hypothesis

After reverse-flow focused validation acceptance, residual fortress/Hy3 rows were
queued as proposal IDs only. Supervisors still lacked an operator-visible package
that selects one residual adjacent row and hands it to
agent_harness_eval_cluster_local_apply with local comparison required while
reverse-flow remains selected and skill unlocks stay closed. Selected-step
adjacent handoff only fires when the selected pipeline step is itself an adjacent
harness-eval row.

## Change set

- build_skill_route_discovery_residual_adjacent_harness_eval_local_apply
- _select_residual_adjacent_harness_eval_proposal_id (prefer fortress, then Hy3)
- Pipeline field residual_adjacent_harness_eval_local_apply
- record helper refreshes residual local apply after focused validation outcomes
- Render path surfaces residual local apply status/decision/selected proposal and prefers its supervisor next action when ready/blocked
- Docs: architecture, skill-route-discovery, self-model
- Tests: residual local apply + focused validation residual path + docs contracts

## Validation

- pytest tests/test_github_growth.py -q -k skill_route residual/focused/unlocked/pipeline: 9 passed
- pytest tests/test_docs_contracts.py -q -k skill_route: 24 passed

## Review notes

- Activation remains external; no push/promotion/restart from this surface
- Residual fortress preferred over Hy3 for harness-eval local apply selection
- Reverse-flow skill unlocks do not transfer to residual rows
- agent-chief-style privacy rows remain review-only
- Distinct from skill_route_discovery_adjacent_harness_eval_handoff (selected-step only)
- Blocked residual queue keeps residual local apply blocked until queue ready
