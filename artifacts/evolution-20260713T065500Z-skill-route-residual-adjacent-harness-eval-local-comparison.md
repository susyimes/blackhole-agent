# Evolution: residual adjacent harness-eval local comparison

Digest: `github-growth-20260712T225308.154547Z`
Proposal: `prop-residual-adjacent-fortress-harness-eval`
Surface: `skill_route_discovery_residual_adjacent_harness_eval_local_comparison`

## Hypothesis

Residual adjacent harness-eval local apply packaged a fortress/Hy3 handoff to
`agent_harness_eval_cluster_local_apply` with supervisor next action
`run_agent_harness_eval_local_comparison_for_residual_adjacent_row`, but did not
emit an operator-visible residual comparison result that unlocks only
documentation/test/code_patch after harness criteria pass.

## What changed

- New controller surface runs residual harness local comparison after residual
  local apply is `ready`
- Decision:
  `unlock_documentation_test_or_code_patch_after_residual_adjacent_harness_local_comparison`
- Supervisor next:
  `apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external`
- Harness post-compare lanes unlock; skill unlocks stay closed
  (`skill_route_discovery_inherited=false`, `skill_route_unlocked_local_lanes=[]`)
- Wired through capability pipeline, record/close refresh, render, docs, tests,
  and self-model

## Safety

- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart remain denied
- agent-chief privacy rows stay review-only
- Body-free exports only (no raw evidence URLs, command text, or upstream bodies)

## Rollback

`refs/blackhole-agent/rollback/20260713T065443Z-residual-adjacent-harness-eval-local-comparison`

Artifact: `artifacts/rollback-20260713T065443Z-residual-adjacent-harness-eval-local-comparison.md`

## Validation

Focused pytest selectors for residual adjacent harness-eval local apply/comparison
and docs skill-route contracts.
