# Evolution: residual adjacent harness-eval local apply

Digest: `github-growth-20260712T223308.255959Z`
Proposal: `prop-residual-adjacent-fortress-harness-eval`
Surface: `skill_route_discovery_residual_adjacent_harness_eval_local_apply`

## Why

Residual adjacent queue packaged fortress/Hy3 IDs after reverse-flow acceptance but
did not select one residual row or emit a local-comparison handoff package for
`agent_harness_eval_cluster_local_apply`.

## What changed

- New controller surface selects one residual proposal (prefer fortress)
- Decision: `hand_off_selected_residual_adjacent_row_to_agent_harness_eval_cluster_local_apply`
- Supervisor next: `run_agent_harness_eval_local_comparison_for_residual_adjacent_row`
- Skill unlocks closed; activation external; body-free exports only
- Wired through capability pipeline, record/close refresh, render, docs, tests

## Validation

9 github_growth skill-route tests + 24 docs skill_route contracts passed.

## Rollback

`refs/blackhole-agent/rollback/20260712T223459Z-residual-adjacent-harness-eval-local-apply`
